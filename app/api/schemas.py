from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class RegisterIn(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=8)


class LoginIn(BaseModel):
    email: str
    password: str


class UserOut(BaseModel):
    id: int
    email: str
    model_config = ConfigDict(from_attributes=True)


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"


class TaskIn(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str | None = None


class TaskStatusIn(BaseModel):
    is_done: bool


class TaskOut(BaseModel):
    id: int
    user_id: int
    title: str
    description: str | None
    is_done: bool
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)
