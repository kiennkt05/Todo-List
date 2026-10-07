from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class User:
    id: int
    email: str
    password_hash: str


@dataclass(frozen=True)
class Task:
    id: int
    user_id: int
    title: str
    description: str | None
    is_done: bool
    created_at: datetime
