from datetime import timezone

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.domain.errors import EmailAlreadyExists
from app.domain.models import Task, User

from .tables import TaskRow, UserRow


def to_user(row: UserRow) -> User:
    return User(row.id, row.email, row.password_hash)


def to_task(row: TaskRow) -> Task:
    created_at = row.created_at
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=timezone.utc)
    return Task(row.id, row.user_id, row.title, row.description, row.is_done, created_at)


class SqlUserRepository:
    def __init__(self, session: Session):
        self.session = session

    def by_email(self, email: str) -> User | None:
        row = self.session.scalar(select(UserRow).where(UserRow.email == email))
        return to_user(row) if row else None

    def add(self, email: str, password_hash: str) -> User:
        row = UserRow(email=email, password_hash=password_hash)
        self.session.add(row)
        try:
            self.session.commit()
        except IntegrityError as exc:
            self.session.rollback()
            raise EmailAlreadyExists("Email already registered") from exc
        return to_user(row)


class SqlTaskRepository:
    def __init__(self, session: Session):
        self.session = session

    def list_for_user(self, user_id: int) -> list[Task]:
        rows = self.session.scalars(
            select(TaskRow)
            .where(TaskRow.user_id == user_id)
            .order_by(TaskRow.id.desc())
        ).all()
        return [to_task(row) for row in rows]

    def by_id_for_user(self, task_id: int, user_id: int) -> Task | None:
        row = self._find(task_id, user_id)
        return to_task(row) if row else None

    def add(self, user_id: int, title: str, description: str | None) -> Task:
        row = TaskRow(user_id=user_id, title=title, description=description, is_done=False)
        self.session.add(row)
        self.session.commit()
        return to_task(row)

    def set_done(self, task_id: int, user_id: int, is_done: bool) -> Task | None:
        row = self._find(task_id, user_id)
        if row is None:
            return None
        row.is_done = is_done
        self.session.commit()
        return to_task(row)

    def delete(self, task_id: int, user_id: int) -> bool:
        row = self._find(task_id, user_id)
        if row is None:
            return False
        self.session.delete(row)
        self.session.commit()
        return True

    def _find(self, task_id: int, user_id: int) -> TaskRow | None:
        return self.session.scalar(
            select(TaskRow).where(TaskRow.id == task_id, TaskRow.user_id == user_id)
        )
