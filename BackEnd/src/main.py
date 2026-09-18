from fastapi import FastAPI, Query, Header, HTTPException, Depends, Request
import os
import uvicorn
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.concurrency import run_in_threadpool
from typing import Optional

from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from jwt_auth import get_current_user_from_token, get_user_from_header

from models import LLMQuery,DropDowndropdownList,HistoryQuery,SaveProjectRequest,LLMConfig,LLMConfigUpdate,ChannelConfig,ChannelConfigUpdate,PromptConfig,PromptConfigUpdate
from config_manager import (
    get_all_llms, create_llm, update_llm, delete_llm,
    get_all_channels, create_channel, update_channel, delete_channel,
    get_all_prompts, create_prompt, update_prompt, delete_prompt
)
from brainstorm_models import BrainstormRequest, SaveBrainstormIdeasRequest, SaveBrainstormIdeasResponse
from generate_items_models import GenerateItemsRequest, GenerateItemsResponse
from generate_project_items import process_generate_project_items 
from business_models import SaveBusinessSurveyRequest, GetBusinessSurveyResponse
from user_models import RegisterUserRequest, RegisterUserResponse, LoginUserRequest, LoginUserResponse
from rag_run import invoke, save_content, content_agent_create
from brainstorm_agent import brainstorm_agent_create, brainstorm_agent_invoke
from story_creation_models import StoryCreationRequest
from story_creation_agent import story_creation_agent_create, story_creation_agent_invoke
from story_ideas import get_story_ideas
from find_your_voice import find_your_voice_invoke, FindYourVoiceRequest
from brainstorm_content_snippet import idea_brainstorm_invoke, IdeaBrainstormRequest, get_brainstorm_content_snippets
from voice_manager import (
    SaveVoiceRequest, UpdateVoiceRequest, SetProjectVoiceRequest,
    save_voice, get_voices, update_voice, delete_voice,
    get_project_voice, set_project_voice,
)
from persist_data import save_project_data, get_project_data, check_item_for_llm_channel
from project_brainstorming_ideas import get_project_brainstorming_ideas_endpoint, save_project_brainstorming_ideas_endpoint
from business_survey import save_business_survey_data, get_business_survey_data
from user_management import register_user as register_user_db, login_user as login_user_db
from db_manager import set_current_user, get_current_user, get_db_connection, ensure_user_defaults_seeded
from prompt import get_prompt_templates
from persist_history import retrieve_query_history
from buttons_handler import get_projects,persist_projects,get_items,persist_items,get_channels,persist_channels,get_llms

from load_channels import main as load_channels
from load_prompts import main as load_prompts
from load_llms import main as load_llms
#from load_knowledgebase import main as load_knowledgebase

app = FastAPI()

# No cross-origin browser access by default. Nothing needs it: the Content Editor
# is served from /www by this same app, and Web talks to the API server-side with
# requests, where CORS never applies. Set LOCOL_CORS_ALLOW_ORIGINS (comma-separated)
# only if you serve the editor from a different origin than the API - i.e. if
# LOCOL_WWW_URL and LOCOL_API_URL point at different hosts.
_cors_origins = [
    origin.strip()
    for origin in os.environ.get("LOCOL_CORS_ALLOW_ORIGINS", "").split(",")
    if origin.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

def _rate_limit_key(request: Request) -> str:
    """Key by the real client IP. BackEnd's public port is only ever reached
    through the k8s ingress, so X-Forwarded-For (set by that trusted hop) is
    safe to trust here; falls back to the socket peer for local/loopback calls."""
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    return request.client.host if request.client else "unknown"

def _user_rate_limit_key(request: Request) -> str:
    """Key the credit-spending endpoints by authenticated user, not by IP.

    A valid token is what spends provider credit, and colleagues behind one NAT
    shouldn't eat each other's budget. Unauthenticated requests fall back to the
    IP key - they are about to 401 in the route's own dependency anyway."""
    user_id = get_user_from_header(request.headers.get("Authorization"))
    return f"user:{user_id}" if user_id else _rate_limit_key(request)

# Per-user ceilings for the endpoints that reach a provider. Far above interactive
# use - a person clicking Submit Prompt manages a handful a minute - and far below
# what a scripted token could burn. The batch limit is separate because
# /api/generate-project-items fans out to one LLM call per selected idea.
LLM_RATE_LIMIT = os.environ.get("LOCOL_LLM_RATE_LIMIT", "20/minute")
LLM_BATCH_RATE_LIMIT = os.environ.get("LOCOL_LLM_BATCH_RATE_LIMIT", "5/minute")

limiter = Limiter(key_func=_rate_limit_key)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)

app.mount("/www", StaticFiles(directory="www"), name="www")

# www/build/ holds the compiled Stencil components that implement <quill-editor> and
# <quill-view>. Without them index.html still loads and the dropdowns still work, but the
# custom elements never register, so writing .content on them is a no-op and the Content
# Editor and History panes render nothing - with no console error and no failed API call.
# That is indistinguishable from a data bug from the browser, so say so loudly at startup.
if not os.path.isdir(os.path.join("www", "build")):
    print(
        "[WARN] www/build/ is missing - the Content Editor will load but render nothing. "
        "Its Quill web components are not built. Run 'npm install && npm run build' in FrontEnd/ "
        "and make sure www/build/ is committed so container images include it."
    )

async def ensure_user_context(user_id: str = Depends(get_current_user_from_token)):
    """Ensure user context is set for database operations using JWT authentication"""
    set_current_user(user_id)
    # Verify the context was set properly
    current = get_current_user()
    if current != user_id:
        raise HTTPException(status_code=500, detail="Failed to set user context")
    # Repair any channels/llms/prompts left missing or empty by a failed registration seed
    await run_in_threadpool(ensure_user_defaults_seeded, user_id)
    return user_id

@app.get("/api/load-buttons/{button}")
async def _load_buttons(button: str, user_id: str = Depends(ensure_user_context)):
    if button == "kb":
        result = "" # load_knowledgebase()
    elif button == "prompts":
        result = load_prompts()
    else:
        result = load_llms()
        result = result + '; ' + load_channels()
    return result


@app.post("/api/llm-invoke/")
@limiter.limit(LLM_RATE_LIMIT, key_func=_user_rate_limit_key)
async def _llm_invoke(request: Request, body: LLMQuery, user_id: str = Depends(ensure_user_context)):
    response = await invoke(body)
    return response

@app.post("/api/persist-content/")
async def _persist_content(body: LLMQuery, user_id: str = Depends(ensure_user_context)):
    response = await save_content(body)
    return response

@app.post("/api/get-history/")
async def _retrieve_query_history(body: HistoryQuery, user_id: str = Depends(ensure_user_context)):
    return retrieve_query_history(body)

@app.get("/api/get-prompt-templates/{selected}")
async def _get_prompt_templates(selected: str, user_id: str = Depends(ensure_user_context)):
    return get_prompt_templates(selected)

@app.post("/api/persist-projects/")
async def _persist_projects(body: DropDowndropdownList, user_id: str = Depends(ensure_user_context)):
    return persist_projects(body.dropdownList)

@app.get("/api/get-projects/")
async def _get_projects(user_id: str = Depends(ensure_user_context)):
    return get_projects()

@app.post("/api/persist-items/")
async def _persist_items(
    body: DropDowndropdownList,
    parent: str = Query(default=""),
    user_id: str = Depends(ensure_user_context)
    ):
    return persist_items(parent,body.dropdownList)

@app.get("/api/get-items/{parent}")
async def _get_items(parent: str, user_id: str = Depends(ensure_user_context)):
    return get_items(parent)

@app.post("/api/persist-channels/")
async def _persist_channels(body: DropDowndropdownList, user_id: str = Depends(ensure_user_context)):
    return persist_channels(body.dropdownList)

@app.get("/api/get-channels/")
async def _get_channels(user_id: str = Depends(ensure_user_context)):
    return get_channels()

@app.get("/api/get-llms/")
async def _get_llms(user_id: str = Depends(ensure_user_context)):
    return get_llms()

# =============================================================================
# Configuration CRUD Endpoints
# =============================================================================

# LLM CRUD
@app.get("/api/llms")
async def _get_all_llms(user_id: str = Depends(ensure_user_context)):
    """Get all LLM configurations"""
    return get_all_llms()

@app.post("/api/llms")
async def _create_llm(config: LLMConfig, user_id: str = Depends(ensure_user_context)):
    """Create a new LLM configuration"""
    return create_llm(config)

@app.put("/api/llms/{llm_id}")
async def _update_llm(llm_id: str, config: LLMConfigUpdate, user_id: str = Depends(ensure_user_context)):
    """Update an LLM configuration"""
    return update_llm(llm_id, config)

@app.delete("/api/llms/{llm_id}")
async def _delete_llm(llm_id: str, user_id: str = Depends(ensure_user_context)):
    """Delete an LLM configuration"""
    return delete_llm(llm_id)

# Channel CRUD
@app.get("/api/channels")
async def _get_all_channels(user_id: str = Depends(ensure_user_context)):
    """Get all channel configurations"""
    return get_all_channels()

@app.post("/api/channels")
async def _create_channel(config: ChannelConfig, user_id: str = Depends(ensure_user_context)):
    """Create a new channel configuration"""
    return create_channel(config)

@app.put("/api/channels/{channel_id}")
async def _update_channel(channel_id: str, config: ChannelConfigUpdate, user_id: str = Depends(ensure_user_context)):
    """Update a channel configuration"""
    return update_channel(channel_id, config)

@app.delete("/api/channels/{channel_id}")
async def _delete_channel(channel_id: str, user_id: str = Depends(ensure_user_context)):
    """Delete a channel configuration"""
    return delete_channel(channel_id)

# Prompt CRUD
@app.get("/api/prompts")
async def _get_all_prompts(user_id: str = Depends(ensure_user_context)):
    """Get all prompt configurations with tags"""
    return get_all_prompts()

@app.post("/api/prompts")
async def _create_prompt(config: PromptConfig, user_id: str = Depends(ensure_user_context)):
    """Create a new prompt configuration"""
    return create_prompt(config)

@app.put("/api/prompts/{prompt_id}")
async def _update_prompt(prompt_id: str, config: PromptConfigUpdate, user_id: str = Depends(ensure_user_context)):
    """Update a prompt configuration"""
    return update_prompt(prompt_id, config)

@app.delete("/api/prompts/{prompt_id}")
async def _delete_prompt(prompt_id: str, user_id: str = Depends(ensure_user_context)):
    """Delete a prompt configuration"""
    return delete_prompt(prompt_id)

def _llm_config_summary(agent):
    """Describe an agent's LLM configuration for a client.

    Never return the LLM instance itself: FastAPI's encoder falls back to vars(),
    and its llm_selected dict holds the *decrypted* APIkey.
    """
    return {
        "success": True,
        "id": agent.llm_selected.get("id"),
        "name": agent.llm_selected.get("name"),
        "model": agent.llm_selected.get("model"),
    }

@app.get("/api/open-llm/{llm}")
async def _open_llm(llm: str, user_id: str = Depends(ensure_user_context)):
    """Validate that the selected LLM is usable.

    Agents are built per request inside rag_run.invoke() now, so nothing is retained
    here - this only surfaces a bad model or key at selection time rather than on the
    user's first Submit Prompt.
    """
    return _llm_config_summary(content_agent_create(llm))

@app.get("/api/open-brainstorm-agent/{llm}")
async def _open_brainstorm_agent(llm: str, user_id: str = Depends(ensure_user_context)):
    """Validate that the selected LLM is usable for brainstorming. Retains nothing."""
    return _llm_config_summary(brainstorm_agent_create(llm))

@app.post("/api/invoke-brainstorm-llm")
@limiter.limit(LLM_RATE_LIMIT, key_func=_user_rate_limit_key)
async def _invoke_brainstorm_agent(request: Request, body: BrainstormRequest, user_id: str = Depends(ensure_user_context)):
    response = await brainstorm_agent_invoke(body)
    return response

@app.get("/api/open-story-creation-agent/{llm}")
async def _open_story_creation_agent(llm: str, user_id: str = Depends(ensure_user_context)):
    """Validate that the selected LLM is usable for story creation. Retains nothing."""
    return _llm_config_summary(story_creation_agent_create(llm))

@app.post("/api/invoke-story-creation-llm")
@limiter.limit(LLM_RATE_LIMIT, key_func=_user_rate_limit_key)
async def _invoke_story_creation_agent(request: Request, body: StoryCreationRequest, user_id: str = Depends(ensure_user_context)):
    response = await story_creation_agent_invoke(body)
    return response

@app.get("/api/get-story-ideas")
async def _get_story_ideas(user_id: str = Depends(ensure_user_context)):
    return {"story_ideas": get_story_ideas()}

@app.post("/api/findYourVoice")
@limiter.limit(LLM_RATE_LIMIT, key_func=_user_rate_limit_key)
async def _find_your_voice(request: Request, body: FindYourVoiceRequest, user_id: str = Depends(ensure_user_context)):
    """Analyze a Reddit user's writing style and recommend a voice prompt"""
    response = await find_your_voice_invoke(body)
    return response

@app.post("/api/brainstorm-idea")
@limiter.limit(LLM_RATE_LIMIT, key_func=_user_rate_limit_key)
async def _brainstorm_idea(request: Request, body: IdeaBrainstormRequest, user_id: str = Depends(ensure_user_context)):
    """Brainstorm on a campaign idea using a custom prompt"""
    response = await idea_brainstorm_invoke(body)
    return response

@app.get("/api/brainstorm-content-snippets")
async def _get_brainstorm_content_snippets(idea_id: str = Query(..., description="Parent idea ID"), user_id: str = Depends(ensure_user_context)):
    """Get all brainstorm content snippets for a given campaign idea"""
    return get_brainstorm_content_snippets(idea_id)

@app.post("/api/voices")
async def _save_voice(body: SaveVoiceRequest, user_id: str = Depends(ensure_user_context)):
    return save_voice(body)

@app.get("/api/voices")
async def _get_voices(user_id: str = Depends(ensure_user_context)):
    return get_voices()

@app.put("/api/voices/{voice_id}")
async def _update_voice(voice_id: str, body: UpdateVoiceRequest, user_id: str = Depends(ensure_user_context)):
    return update_voice(voice_id, body)

@app.delete("/api/voices/{voice_id}")
async def _delete_voice(voice_id: str, user_id: str = Depends(ensure_user_context)):
    return delete_voice(voice_id)

@app.get("/api/projects/{project_id}/voice")
async def _get_project_voice(project_id: str, user_id: str = Depends(ensure_user_context)):
    """The voice a project's content is generated in, or {} if none is selected"""
    return get_project_voice(project_id)

@app.put("/api/projects/{project_id}/voice")
async def _set_project_voice(project_id: str, body: SetProjectVoiceRequest, user_id: str = Depends(ensure_user_context)):
    """Select (or clear, with a null voice_id) the voice a project generates in"""
    return set_project_voice(project_id, body)

@app.post("/api/save-project")
async def _save_project(body: SaveProjectRequest, user_id: str = Depends(ensure_user_context)):
    """Save project survey data"""
    result = save_project_data(body.project_id, body.survey_type, body.survey_data, body.question_set)
    return result

@app.get("/api/get-project")
async def _get_project(id: str = Query(..., description="Project ID"), user_id: str = Depends(ensure_user_context)):
    """Get project data by ID"""
    result = get_project_data(id)
    return result

@app.get("/api/get-project-brainstorming-ideas")
async def get_project_brainstorming_ideas_route(project_id: str = Query(..., description="Project ID"), user_id: str = Depends(ensure_user_context)):
    return await get_project_brainstorming_ideas_endpoint(project_id, user_id)

@app.post("/api/save-project-brainstorming-ideas", response_model=SaveBrainstormIdeasResponse)
async def save_project_brainstorming_ideas_route(request: SaveBrainstormIdeasRequest, user_id: str = Depends(ensure_user_context)):
    return await save_project_brainstorming_ideas_endpoint(request, user_id)

@app.post("/api/generate-project-items", response_model=GenerateItemsResponse)
@limiter.limit(LLM_BATCH_RATE_LIMIT, key_func=_user_rate_limit_key)
async def generate_project_items_endpoint(request: Request, body: GenerateItemsRequest, user_id: str = Depends(ensure_user_context)):
    """Generate and merge project items from selected ideas.

    One LLM call per selected idea, so this gets the lower batch limit - and
    GenerateItemsRequest caps selected_ideas, without which a single request
    could ask for an unbounded number of generations. The body parameter is
    named 'body' rather than 'request' because slowapi requires the Starlette
    Request under that name."""
    return await process_generate_project_items(body)

@app.post("/api/save-business-survey")
async def _save_business_survey(body: SaveBusinessSurveyRequest, user_id: str = Depends(ensure_user_context)):
    """Save business survey data"""
    result = save_business_survey_data(body)
    return result

@app.get("/api/get-business-survey")
async def _get_business_survey(user_id: str = Depends(ensure_user_context)):
    """Get the business survey data"""
    result = get_business_survey_data()
    return result

@app.get("/api/check-item-llm-channel/{item_id}")
async def _check_item_for_llm_channel(item_id: str, user_id: str = Depends(ensure_user_context)):
    """Check what LLM and channel combinations are available for a specific item"""
    try:
        combinations = check_item_for_llm_channel(item_id)
        return {
            "success": True,
            "item_id": item_id,
            "combinations": combinations,
            "count": len(combinations)
        }
    except Exception as e:
        return {
            "success": False,
            "item_id": item_id,
            "error": str(e),
            "combinations": []
        }

@app.post("/api/register-user", response_model=RegisterUserResponse)
@limiter.limit("5/hour")
async def register_user_endpoint(request: Request, body: RegisterUserRequest):
    """Register a new user"""
    return await run_in_threadpool(register_user_db, body)

@app.post("/api/login-user", response_model=LoginUserResponse)
@limiter.limit("10/minute")
async def login_user_endpoint(request: Request, body: LoginUserRequest):
    """Login user authentication"""
    response = await run_in_threadpool(login_user_db, body)

    # If login successful and authenticated, the web frontend should create the JWT token
    # The backend just returns the user_id for the web to create the token
    return response

# SECURITY NOTE: The following administrative endpoints have been removed for security:
# - /api/recreate-users-table - Could delete all user data (no authentication)
# - /api/init-user-database/{user_id} - Could create arbitrary user databases (no authentication)
# - /api/set-current-user/{user_id} - Could enable user impersonation (no authentication)
# - /api/current-user - Reported session state with no authentication (no authentication)
#
# recreate_users_table() has since been deleted outright - it dropped the users table and
# reissued every id, which orphans each db/users/<user_id>.sqlite, since those files are
# named by user id. The remaining two functions are still used internally:
# init_user_database is called automatically during user registration, and
# set_current_user is called automatically via JWT authentication in ensure_user_context.
# The users table itself is created by scripts/create_user_database.py at setup, and
# re-created if absent by init_users_table() on register/login.
#
# /api/current-user was deleted rather than given the ensure_user_context dependency
# every other /api route has. Authenticating it would have made it echo back the
# user_id from the token the caller just presented - no information they did not
# already hold - so there was nothing left worth exposing. Nothing called it: not Web,
# not the Content Editor JS, not QualityAssurance. get_current_user() itself is still
# used below, inside ensure_user_context. tests/test_route_auth.py now asserts that
# every /api route carries the dependency, so the next endpoint added without it fails
# the suite instead of going unnoticed.

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=int(os.environ.get("LOCOL_BACKEND_PORT", "8000")), reload=True)