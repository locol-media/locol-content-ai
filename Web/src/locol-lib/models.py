from pydantic import BaseModel, Field
from typing import List,Optional
from datetime import datetime

class DropDownItem(BaseModel):
    id: str
    name: str
    parent: Optional[str] = None
    create_datetime: Optional[datetime] = None
    replace_datetime: Optional[datetime] = None

class DropDowndropdownList(BaseModel):
    dropdownList: List[DropDownItem]