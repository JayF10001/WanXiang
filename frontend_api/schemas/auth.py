from pydantic import BaseModel
from typing import Optional


class LoginRequest(BaseModel):
    email: str
    password: str
    type: str = "account"


class RegisterRequest(BaseModel):
    email: str
    password: str
    username: str
    inviteCode: Optional[str] = ""


class UserResponse(BaseModel):
    id: str
    name: str
    email: str
    role: str
    avatar: Optional[str] = None
