from generate_items_models import GenerateItemsRequest, GenerateItemsResponse
from buttons_handler import get_items, persist_items
from prompt import get_prompt_template_by_platform
from rag_run import invoke
from models import LLMQuery, DropDownItem
from datetime import datetime
from db_manager import get_db_connection
import logging
import os

logger = logging.getLogger(__name__)

# Debug mode flag
DEBUG = os.environ.get("DEBUG", "").lower() in ("true", "1", "yes")


async def process_generate_project_items(request: GenerateItemsRequest) -> GenerateItemsResponse:
    """
    Process generate project items request by merging selected ideas with existing project items
    
    Parameters:
        request (GenerateItemsRequest): The request containing project_id and selected_ideas
        
    Returns:
        GenerateItemsResponse: Success/error response with item count
    """
    try:
        # Get existing items for the project
        existing_items = get_items(request.project_id)
        
        # Create a dictionary for quick lookup by ID
        items_dict = {item.get('id'): item for item in existing_items if item.get('id')}
        
        # Create a separate dictionary to track only the processed items for return
        processed_items_dict = {}
        
        # Process each selected idea
        for selected_idea in request.selected_ideas:
            idea_dict = selected_idea.dict()
            
            # Get prompt template for the platform
            prompt_template = get_prompt_template_by_platform(selected_idea.platform)

            if prompt_template:
                # Call rag_run.invoke with the parameters
                try:
                    # Look up channel_id from platform name (platform contains channel name)
                    conn = get_db_connection()
                    cursor = conn.cursor()
                    cursor.execute("SELECT id FROM channels WHERE name = ?", (selected_idea.platform,))
                    channel_row = cursor.fetchone()
                    conn.close()

                    # Use channel_id if found, otherwise use platform name as fallback
                    channel_id = channel_row[0] if channel_row else selected_idea.platform

                    # Create context from business and strategic survey data
                    context_parts = []
                    if request.business_survey:
                        context_parts.append(f"Business Survey: {request.business_survey}")
                    if request.strategic_survey:
                        context_parts.append(f"Strategic Survey: {request.strategic_survey}")

                    context = "\n".join(context_parts)

                    # Replace placeholders in the prompt template with idea details
                    merged_template = prompt_template['template'].format(
                        Title=selected_idea.title,
                        Description=selected_idea.description,
                        Goal=selected_idea.goal,
                        Platform=selected_idea.platform,
                        ContentType=selected_idea.content_type
                    )

                    # Form the question with context prefix
                    question = f"{context}\n\n{merged_template}"

                    # Create LLMQuery object for rag_run.invoke
                    llm_query = LLMQuery(
                        project_id=request.project_id,
                        item_id=selected_idea.id,
                        channel_id=channel_id,
                        prompt_id=prompt_template['id'],
                        content=context,
                        fields="",
                        llm="default",
                        prompt_template=prompt_template['template'],
                        query=question,
                        panel_fractions="",
                        rag_on_off=True,
                        voice_id=request.voice_id
                    )
                    
                    # Invoke the content-generation agent
                    rag_result = await invoke(llm_query)
                    
                    # Add the generated content to the idea
                    idea_dict['generated_content'] = rag_result.output if hasattr(rag_result, 'output') else str(rag_result)
                    idea_dict['prompt_template_used'] = prompt_template['name']
                    idea_dict['timestamp'] = rag_result.timestamp if hasattr(rag_result, 'timestamp') else None
                    
                except Exception as e:
                    error_msg = f"Error generating content for idea {selected_idea.id}: {str(e)}"
                    logger.error(error_msg, exc_info=DEBUG)
                    idea_dict['generated_content'] = None
                    idea_dict['generation_error'] = str(e)
            else:
                error_msg = f"No prompt template found for platform: {selected_idea.platform}"
                logger.warning(error_msg)
                idea_dict['generated_content'] = None
                idea_dict['generation_error'] = error_msg
            
            # Check if item already exists in project
            if idea_dict['id'] in items_dict:
                # Update existing item
                items_dict[idea_dict['id']].update(idea_dict)
            else:
                # Add new item to dictionary
                items_dict[idea_dict['id']] = idea_dict
            
            # Add the processed item to the return dictionary
            processed_items_dict[idea_dict['id']] = items_dict[idea_dict['id']].copy()
        
        # Convert to DropDownItem list for persistence
        current_datetime = datetime.now().isoformat()
        dropdown_items = []
        
        for item_data in items_dict.values():
            # Check if this is a new item (doesn't have create_datetime)
            if 'create_datetime' not in item_data:
                item_data['create_datetime'] = current_datetime
            
            # Items in this batch carry 'title' (from SelectedIdea); pre-existing rows
            # loaded from the DB only carry 'name'. Fall back so untouched siblings keep
            # their name instead of being blanked by the delete-and-reinsert below.
            item_name = item_data.get('title') or item_data.get('name') or ''
            if not item_name:
                logger.warning(
                    "Item %s in project %s has neither title nor name; persisting a blank name",
                    item_data.get('id'), request.project_id
                )

            dropdown_item = DropDownItem(
                id=item_data['id'],
                name=item_name,  # Use title as name
                parent=request.project_id,
                create_datetime=item_data.get('create_datetime', current_datetime),
                replace_datetime=current_datetime
            )
            dropdown_items.append(dropdown_item)
        
        # Persist the list of DropDownItem objects
        persist_items(request.project_id, dropdown_items)
        
        return GenerateItemsResponse(
            success=True,
            message=f"Successfully processed {len(request.selected_ideas)} items for project {request.project_id}",
            data={"items_count": len(processed_items_dict), "items_dict": processed_items_dict}
        )
        
    except Exception as e:
        return GenerateItemsResponse(
            success=False,
            message="Failed to generate project items",
            error=str(e)
        )