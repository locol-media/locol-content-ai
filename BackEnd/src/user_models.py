from pydantic import BaseModel
from typing import Optional

class RegisterUserRequest(BaseModel):
    username: str
    email: str
    password: str
    created_at: str

class RegisterUserResponse(BaseModel):
    success: bool
    message: str
    user_id: Optional[str] = None
    error: Optional[str] = None

class LoginUserRequest(BaseModel):
    username: str
    password: str

class LoginUserResponse(BaseModel):
    success: bool
    authenticated: bool
    message: str
    user_id: Optional[str] = None
    jwt_token: Optional[str] = None
    error: Optional[str] = None