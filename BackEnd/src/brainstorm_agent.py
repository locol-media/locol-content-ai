from llm import LLM
from brainstorm_models import BrainstormRequest
import uuid
from project_brainstorming_ideas import save_project_brainstorm_idea
from db_manager import get_db_connection
from load_prompts import sync_prompts_table

def ensure_prompts_tables_exist():
    """Create prompts and prompt_tags tables if they don't exist"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Create prompts table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS prompts (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            template TEXT NOT NULL
        )
    ''')
    
    # Create prompt_tags table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS prompt_tags (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            prompt_id TEXT NOT NULL,
            tag TEXT NOT NULL,
            FOREIGN KEY (prompt_id) REFERENCES prompts (id)
        )
    ''')
    
    conn.commit()
    conn.close()

def brainstorm_agent_create(llm_name):
    """Build a brainstorm agent for the calling request.

    Request-scoped on purpose - see content_agent_create() in rag_run.py."""
    system_prompt = "Please create output as a json array list named brainstorm_ideas"
    return LLM(llm_name, system_prompt)

def _create_brainstorm_prompt(brainstorm_request: BrainstormRequest) -> str:
    """Create a comprehensive prompt from the brainstorm request data"""
    
    business = brainstorm_request.business_survey
    strategic = brainstorm_request.strategic_survey
    
    prompt_parts = []
    
    # Business Context
    if business.get('business_name'):
        prompt_parts.append(f"Business: {business['business_name']}")
    
    if business.get('business_description'):
        prompt_parts.append(f"Description: {business['business_description']}")
    
    if business.get('industry'):
        prompt_parts.append(f"Industry: {business['industry']}")
    
    if business.get('target_audience'):
        prompt_parts.append(f"Target Audience: {business['target_audience']}")
    
    if business.get('services'):
        prompt_parts.append(f"Services: {business['services']}")
    
    if business.get('unique_value'):
        prompt_parts.append(f"Unique Value: {business['unique_value']}")
    
    # Goals and Strategy
    if business.get('business_goals'):
        goals = business['business_goals']
        if isinstance(goals, list):
            prompt_parts.append(f"Business Goals: {', '.join(goals)}")
        else:
            prompt_parts.append(f"Business Goals: {goals}")
    
    # Customer Insights
    if business.get('customer_challenges'):
        prompt_parts.append(f"Customer Challenges: {business['customer_challenges']}")
    
    if business.get('audience_interests'):
        prompt_parts.append(f"Audience Interests: {business['audience_interests']}")
    
    # Content Preferences
    if business.get('content_preference'):
        prompt_parts.append(f"Content Style: {business['content_preference']}")
    
    if business.get('content_types'):
        content_types = business['content_types']
        if isinstance(content_types, list):
            prompt_parts.append(f"Content Types: {', '.join(content_types)}")
        else:
            prompt_parts.append(f"Content Types: {content_types}")
    
    # Strategic Insights
    strategic_insights = []
    for key, value in strategic.items():
        if value:
            # Convert snake_case to readable format
            question = key.replace('_', ' ').title()
            strategic_insights.append(f"{question}: {value}")
    
    if strategic_insights:
        prompt_parts.append("Strategic Insights:")
        prompt_parts.extend(strategic_insights)
    
    # Create the final prompt
    business_context = "\n".join(prompt_parts)
    
    final_prompt = f"""
Based on the following business information, generate creative content ideas for brainstorming:

{business_context}

Please generate a diverse set of content ideas that align with the business goals, target audience, and strategic insights provided. Focus on actionable, specific content concepts that would resonate with the target audience and support the business objectives.
Start the project with the first content idea being an introduction of the series. If there is a list of ideas provided, generate an item for each idea.


Return your response as a JSON array with the key "brainstorm_ideas", where each idea includes:
- title: A compelling headline or title
- description: A brief description of the content concept
- content_type: The type of Reddit post (text post, link post, discussion, AMA, how-to, story, etc.)
- platform: Reddit
- goal: Which business goal this supports
"""
    
    return final_prompt

async def brainstorm_agent_invoke(brainstorm_request: BrainstormRequest):
    # BrainstormRequest carries no LLM id, so this always runs on the "default"
    # configuration - but resolved against the requesting user's own llms table.
    brainstorm_agent = brainstorm_agent_create("default")

    # Note: Prompts tables are pre-created and loaded during user database initialization in db_manager.py

    prompt = _create_brainstorm_prompt(brainstorm_request)
    result = await brainstorm_agent.invoke(prompt)
    llm_data = result
    if llm_data:
    # Extract brainstorm_ideas JSON from output string if present
        llm_data = result.output if hasattr(result, 'output') else {}
        try:
            import json
            import re
            # Remove newlines and extract JSON
            output_str = llm_data.replace('\n', '').replace('\r', '')
            # Try to find JSON pattern for brainstorm_ideas
            json_match = re.search(r'\{.*"brainstorm_ideas".*\}', output_str)
            if json_match:
                extracted_json = json.loads(json_match.group())
                llm_data = extracted_json
        except (json.JSONDecodeError, AttributeError, KeyError):
            pass  # Fall back to original llm_data
        
        # Save brainstorm ideas to database
        if isinstance(llm_data, dict) and 'brainstorm_ideas' in llm_data:
            project_id = brainstorm_request.project_id
            brainstorm_ideas = llm_data['brainstorm_ideas']
            
            # Save each idea with a unique ID
            for idea in brainstorm_ideas:
                idea_id = str(uuid.uuid4())
                idea['id'] = idea_id
                save_project_brainstorm_idea(project_id, idea_id, idea)
        
        return llm_data