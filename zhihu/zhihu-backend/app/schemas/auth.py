from pydantic import BaseModel
from typing import Optional


class LoginRequest(BaseModel):
    username: str
    password: str


class RegisterRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    user_id: int
    username: str
    is_demo: bool
    is_admin: bool = False


class UserResponse(BaseModel):
    id: int
    username: str
    is_demo: bool
    is_admin: bool = False
    is_active: bool

    class Config:
        from_attributes = True
