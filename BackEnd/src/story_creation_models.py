# story_creation_models.py - Pydantic models for story creation agent

from pydantic import BaseModel, Field
from typing import Dict, Any
from datetime import datetime


class StoryCreationRequest(BaseModel):
    """Request model for the story creation agent"""
    business_survey: Dict[str, Any] = Field(..., description="Business survey data including skills and hobbies")
    timestamp: str = Field(default_factory=lambda: datetime.now().isoformat())
