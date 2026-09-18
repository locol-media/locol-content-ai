"""
Simplified Pydantic models for the brainstorm LLM endpoint with combined data
"""
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List
from datetime import datetime
from enum import Enum

class RequestType(str, Enum):
    """Type of brainstorm request"""
    CONTENT_BRAINSTORM = "content_brainstorm"
    STRATEGIC_BRAINSTORM = "strategic_brainstorm"


class StrategicSurveyField(BaseModel):
    """Strategic survey field with question, value, and category"""
    question: str
    value: Optional[str] = None
    category: Optional[str] = None


class BrainstormRequest(BaseModel):
    """Simplified request object for the brainstorm LLM endpoint"""
    project_id: str
    business_survey: dict
    strategic_survey: Dict[str, StrategicSurveyField] 
    timestamp: str = Field(default_factory=lambda: datetime.now().isoformat())
    request_type: RequestType = RequestType.CONTENT_BRAINSTORM
    
    class Config:
        use_enum_values = True
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


# Example usage
if __name__ == "__main__":
    import json
    
    # Create example request
    example_request = BrainstormRequest(
        business_survey={
            "business_name": "TechStart Solutions",
            "business_description": "We provide AI-powered business automation tools for small and medium enterprises.",
            "industry": "SaaS/Technology",
            "target_audience": "Small business owners, operations managers",
            "business_goals": ["Lead Generation", "Brand Awareness"]
        },
        strategic_survey={
            "problem_solving": StrategicSurveyField(
                question="What specific problem were you trying to solve when you first created this product?",
                value="I was frustrated seeing small businesses struggle with manual tasks",
                category="emotional_triggers"
            ),
            "customer_story": StrategicSurveyField(
                question="Can you share a customer story that gave you goosebumps?",
                value="A restaurant owner told me our system helped her reclaim 15 hours per week",
                category="emotional_triggers"
            )
        },
        request_type=RequestType.STRATEGIC_BRAINSTORM
    )
    
    # Convert to JSON
    json_output = example_request.model_dump_json(indent=2)
    print("Example JSON Request:")
    print(json_output)
    
    # Generate JSON Schema
    schema = BrainstormRequest.model_json_schema()
    print("\nJSON Schema:")
    print(json.dumps(schema, indent=2))


class BrainstormIdea(BaseModel):
    """Individual brainstorm idea object"""
    id: str
    title: str
    description: str
    content_type: str
    platform: str
    goal: str


class SaveBrainstormIdeasRequest(BaseModel):
    """Request object for the save-project-brainstorming-ideas endpoint"""
    project_id: str = Field(..., description="The project ID to save ideas for")
    brainstorm_ideas: List[BrainstormIdea] = Field(..., description="Array of brainstorm idea objects")
    timestamp: str = Field(default_factory=lambda: datetime.now().isoformat())
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


class SaveBrainstormIdeasResponse(BaseModel):
    """Response object for the save-project-brainstorming-ideas endpoint"""
    success: bool
    message: str
    error: Optional[str] = None

