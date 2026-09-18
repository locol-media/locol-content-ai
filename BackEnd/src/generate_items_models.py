"""
Simple Pydantic models for the generate-project-items endpoint
"""
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List
from datetime import datetime


# Ceiling on one batch. process_generate_project_items() makes one LLM call per
# idea, so an uncapped list is an unbounded number of billable generations that no
# per-request rate limit can contain. Web mirrors this value in its own copy of
# this model so the user gets a clear message instead of a 422.
MAX_IDEAS_PER_BATCH = 25


class SelectedIdea(BaseModel):
    """Individual selected idea object"""
    id: str
    title: str
    description: str
    content_type: str
    platform: str
    goal: str


class GenerateItemsRequest(BaseModel):
    """Request object for the generate-project-items endpoint"""
    project_id: str = Field(..., description="The project ID to generate items for")
    business_survey: Dict[str, Any] = Field(default_factory=dict, description="Business survey data with value fields")
    strategic_survey: Dict[str, Any] = Field(default_factory=dict, description="Strategic survey data")
    selected_ideas: List[SelectedIdea] = Field(
        default_factory=list,
        max_length=MAX_IDEAS_PER_BATCH,
        description=f"Array of selected idea objects (max {MAX_IDEAS_PER_BATCH} - one LLM call each)"
    )
    voice_id: Optional[str] = Field(default=None, description="Saved voice to write every draft in")
    timestamp: str = Field(default_factory=lambda: datetime.now().isoformat())
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


class GenerateItemsResponse(BaseModel):
    """Response object for the generate-project-items endpoint"""
    success: bool
    message: str
    data: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


class BrainstormIdea(BaseModel):
    """Individual brainstorm idea object"""
    id: str
    title: str
    description: str
    content_type: str
    platform: str
    goal: str


# Example usage
if __name__ == "__main__":
    import json
    
    # Create example request
    example_request = GenerateItemsRequest(
        project_id="proj_123456",
        business_survey={
            "business_name": "TechStart Solutions",
            "industry": "SaaS/Technology",
            "target_audience": "Small business owners",
            "business_goals": ["Lead Generation", "Brand Awareness"]
        },
        strategic_survey={
            "problem_solving": {
                "question": "What specific problem were you trying to solve?",
                "value": "Manual processes eating up time",
                "category": "emotional_triggers"
            }
        },
        selected_ideas=[
            SelectedIdea(
                id="idea_1",
                title="Automation tips for small businesses",
                description="Blog post about time-saving automation",
                content_type="blog_post",
                platform="linkedin",
                goal="lead_generation"
            ),
            SelectedIdea(
                id="idea_2",
                title="ROI calculator for time savings",
                description="Interactive tool for calculating ROI",
                content_type="tool",
                platform="website",
                goal="brand_awareness"
            )
        ]
    )
    
    # Convert to JSON
    json_output = example_request.model_dump_json(indent=2)
    print("Example JSON Request:")
    print(json_output)
    
    # Generate JSON Schema
    schema = GenerateItemsRequest.model_json_schema()
    print("\nJSON Schema:")
    print(json.dumps(schema, indent=2))
    
    # Example save brainstorm ideas request
    save_request = SaveBrainstormIdeasRequest(
        project_id="proj_123456",
        brainstorm_ideas=[
            BrainstormIdea(
                id="idea_1",
                title="Automation tips for small businesses",
                description="Blog post about time-saving automation",
                content_type="blog_post",
                platform="linkedin",
                goal="lead_generation"
            ),
            BrainstormIdea(
                id="idea_2",
                title="ROI calculator for time savings", 
                description="Interactive tool for calculating ROI",
                content_type="tool",
                platform="website",
                goal="brand_awareness"
            )
        ]
    )
    
    print("\nSave Brainstorm Ideas Request:")
    print(save_request.model_dump_json(indent=2))