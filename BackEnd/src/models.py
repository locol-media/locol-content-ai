from pydantic import BaseModel, Field
from typing import List,Optional,Dict,Any
from datetime import datetime

class LLMQuery(BaseModel):
    project_id: str
    item_id: str
    channel_id: str
    prompt_id: Optional[str] = None
    content: str
    fields: str
    llm: str
    prompt_template: str
    query: str
    panel_fractions: str
    rag_on_off: bool
    # Saved voice to write in, resolved to its prompt text at generation time.
    # Optional: the Content Editor front end doesn't send one.
    voice_id: Optional[str] = None

class LLMResponse(BaseModel):
    content: str
    timestamp: datetime
    output: str

class HistoryQuery(BaseModel):
    project_id: str
    item_id: str
    channel_id: str

class DropDownItem(BaseModel):
    id: str
    name: str
    parent: Optional[str] = None
    create_datetime: Optional[datetime] = None
    replace_datetime: Optional[datetime] = None

class DropDowndropdownList(BaseModel):
    dropdownList: List[DropDownItem]

class ChannelList(BaseModel):
    channelList: List[str]

class SaveProjectRequest(BaseModel):
    project_id: str
    survey_type: str
    survey_data: Dict[str, Any]
    question_set: Optional[str] = None
    timestamp: Optional[str] = None

# =============================================================================
# Configuration CRUD Models
# =============================================================================

class LLMConfig(BaseModel):
    id: str
    name: str
    APIstyle: str
    APIkey: Optional[str] = None
    APIurl: Optional[str] = None
    model: Optional[str] = None

class LLMConfigUpdate(BaseModel):
    name: Optional[str] = None
    APIstyle: Optional[str] = None
    APIkey: Optional[str] = None
    APIurl: Optional[str] = None
    model: Optional[str] = None

class ChannelConfig(BaseModel):
    id: str
    name: str
    parent: Optional[str] = None

class ChannelConfigUpdate(BaseModel):
    name: Optional[str] = None
    parent: Optional[str] = None

class PromptConfig(BaseModel):
    id: str
    name: str
    template: str
    tags: Optional[List[str]] = None

class PromptConfigUpdate(BaseModel):
    name: Optional[str] = None
    template: Optional[str] = None
    tags: Optional[List[str]] = None