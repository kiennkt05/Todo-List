import re

from .errors import EmailAlreadyExists, InvalidCredentials, InvalidInput, TaskNotFound
from .models import Task, User
from .ports import PasswordHasher, TaskRepository, TokenIssuer, UserRepository


class AuthService:
    def __init__(self, users: UserRepository, passwords: PasswordHasher, tokens: TokenIssuer):
        self.users = users
        self.passwords = passwords
        self.tokens = tokens

    def register(self, email: str, password: str) -> User:
        email = email.strip().lower()
        if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email) or len(password) < 8:
            raise InvalidInput("Valid email and password of at least 8 characters required")
        if self.users.by_email(email):
            raise EmailAlreadyExists("Email already registered")
        return self.users.add(email, self.passwords.hash(password))

    def login(self, email: str, password: str) -> str:
        user = self.users.by_email(email.strip().lower())
        if user is None or not self.passwords.verify(password, user.password_hash):
            raise InvalidCredentials("Invalid email or password")
        return self.tokens.issue(user.id)


class TaskService:
    def __init__(self, tasks: TaskRepository):
        self.tasks = tasks

    def list_tasks(self, user_id: int) -> list[Task]:
        return self.tasks.list_for_user(user_id)

    def create_task(self, user_id: int, title: str, description: str | None) -> Task:
        title = title.strip()
        description = description.strip() if description is not None else None
        if not title:
            raise InvalidInput("Title cannot be blank")
        return self.tasks.add(user_id, title, description or None)

    def get_task(self, user_id: int, task_id: int) -> Task:
        task = self.tasks.by_id_for_user(task_id, user_id)
        if task is None:
            raise TaskNotFound("Task not found")
        return task

    def set_done(self, user_id: int, task_id: int, is_done: bool) -> Task:
        task = self.tasks.set_done(task_id, user_id, is_done)
        if task is None:
            raise TaskNotFound("Task not found")
        return task

    def delete_task(self, user_id: int, task_id: int) -> None:
        if not self.tasks.delete(task_id, user_id):
            raise TaskNotFound("Task not found")
