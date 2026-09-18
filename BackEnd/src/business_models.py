# business_models.py - Pydantic models for business survey API calls

from pydantic import BaseModel, Field
from typing import Optional, Dict, Any
from datetime import datetime


class SaveBusinessSurveyRequest(BaseModel):
    """Request model for saving business survey data"""
    survey_data: Dict[str, Any] = Field(..., description="Business survey form data")
    timestamp: str = Field(..., description="ISO format timestamp when data was saved")


class SaveBusinessSurveyResponse(BaseModel):
    """Response model for saving business survey data"""
    success: bool = Field(..., description="Whether the save operation was successful")
    message: str = Field(..., description="Success or error message")
    survey_id: Optional[str] = Field(None, description="Unique identifier for the saved survey")
    timestamp: Optional[str] = Field(None, description="Server timestamp of when data was saved")


class GetBusinessSurveyResponse(BaseModel):
    """Response model for retrieving business survey data"""
    success: bool = Field(..., description="Whether the retrieval was successful")
    survey_data: Optional[Dict[str, Any]] = Field(None, description="Business survey form data")
    last_updated: Optional[str] = Field(None, description="ISO format timestamp of last update")
    survey_id: Optional[str] = Field(None, description="Unique identifier for the survey")


class BusinessSurveyError(BaseModel):
    """Error model for business survey operations"""
    error_code: str = Field(..., description="Error code")
    error_message: str = Field(..., description="Human readable error message")
    details: Optional[Dict[str, Any]] = Field(None, description="Additional error details")


def extract_survey_values(raw_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Extract clean values from raw StreamlitSurvey data format.
    Handles the {value: ..., timestamp: ...} field object format.
    """
    clean_data = {}
    for field_name, field_data in raw_data.items():
        if field_data is None:
            clean_data[field_name] = None
        elif isinstance(field_data, dict) and 'value' in field_data:
            clean_data[field_name] = field_data['value']
        elif isinstance(field_data, (str, list, int, float, bool)):
            clean_data[field_name] = field_data
        else:
            clean_data[field_name] = str(field_data)
    return clean_data


def prepare_survey_for_api(survey_data: Dict[str, Any]) -> SaveBusinessSurveyRequest:
    """Prepare survey data for API submission"""
    clean_data = extract_survey_values(survey_data)
    return SaveBusinessSurveyRequest(
        survey_data=clean_data,
        timestamp=datetime.now().isoformat()
    )
