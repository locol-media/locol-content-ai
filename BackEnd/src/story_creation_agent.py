"""
Story creation agent — generates personal story ideas from survey skills and hobbies
"""
import json
import re
import uuid
from llm import LLM
from story_creation_models import StoryCreationRequest
from story_ideas import save_story_idea

def story_creation_agent_create(llm_name):
    """Build a story-creation agent for the calling request.

    Request-scoped on purpose - see content_agent_create() in rag_run.py."""
    system_prompt = "Please create output as a json array list named story_ideas"
    return LLM(llm_name, system_prompt, tools=[])


def _create_story_prompt(request: StoryCreationRequest) -> str:
    survey = request.business_survey
    parts = []

    for key in ['business_name', 'target_audience', 'industry']:
        if survey.get(key):
            parts.append(f"{key.replace('_', ' ').title()}: {survey[key]}")

    for key in ['professional_expertise', 'years_experience', 'technical_skills',
                'credentials', 'problems_solved', 'unique_approach', 'industry_mistakes']:
        if survey.get(key):
            parts.append(f"{key.replace('_', ' ').title()}: {survey[key]}")

    for key in ['personal_hobbies', 'active_hobbies', 'creative_hobbies',
                'learning_interests', 'hobby_communities', 'hobbies_and_business', 'audience_overlap']:
        if survey.get(key):
            parts.append(f"{key.replace('_', ' ').title()}: {survey[key]}")

    context = "\n".join(parts)

    return f"""
Based on the following personal background, generate story ideas the business owner could share with their target audience:

{context}

Generate a diverse 3-5 set of personal story ideas that blend the owner's professional expertise and hobbies.
Each story should feel authentic and create a genuine connection with the target audience.
Mix skill-based stories (lessons learned, mistakes made, client wins, unique approaches) with hobby-based stories (what hobbies taught them about business, crossover insights, unexpected parallels).

Each story will become a series of blog posts published on Reddit.

Return as JSON with key "story_ideas", where each item includes:
- title: compelling story headline
- story_angle: how to frame it as a personal narrative
- why_relevant: why the target audience will care
- reddit_post_topics: a list of 3 specific Reddit post topic ideas that break this story into a series, including the subreddits they would fit best.
- for each topic (topic_title), describe relevence to story (relevance_to_story), and list subreddits that might be interested (subreddits).
- source: skill or hobby
- target_emotion: Inspire / Educate / Entertain
"""


async def story_creation_agent_invoke(request: StoryCreationRequest):
    # StoryCreationRequest carries no LLM id, so this always runs on the "default"
    # configuration - but resolved against the requesting user's own llms table.
    story_creation_agent = story_creation_agent_create("default")

    prompt = _create_story_prompt(request)
    result = await story_creation_agent.invoke(prompt)
    llm_data = result.output if hasattr(result, 'output') else {}

    try:
        output_str = llm_data.replace('\n', '').replace('\r', '')
        json_match = re.search(r'\{.*"story_ideas".*\}', output_str)
        if json_match:
            llm_data = json.loads(json_match.group())
    except (json.JSONDecodeError, AttributeError):
        pass

    if isinstance(llm_data, dict) and 'story_ideas' in llm_data:
        delete_story_ideas_on_regenerate()
        for idea in llm_data['story_ideas']:
            idea_id = str(uuid.uuid4())
            idea['id'] = idea_id
            save_story_idea(idea_id, idea)

    return llm_data


def delete_story_ideas_on_regenerate():
    from story_ideas import delete_story_ideas
    delete_story_ideas()
