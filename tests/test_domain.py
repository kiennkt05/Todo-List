import unittest
from datetime import datetime, timezone

from app.domain.errors import EmailAlreadyExists, InvalidCredentials, InvalidInput, TaskNotFound
from app.domain.models import Task, User
from app.domain.services import AuthService, TaskService


class MemoryUsers:
    def __init__(self):
        self.users = {}

    def by_email(self, email):
        return self.users.get(email)

    def add(self, email, password_hash):
        user = User(len(self.users) + 1, email, password_hash)
        self.users[email] = user
        return user


class FakeHasher:
    def hash(self, password):
        return f"hashed:{password}"

    def verify(self, password, stored):
        return stored == self.hash(password)


class FakeTokens:
    def issue(self, user_id):
        return f"token:{user_id}"


class MemoryTasks:
    def __init__(self):
        self.tasks = {}

    def list_for_user(self, user_id):
        return [task for task in self.tasks.values() if task.user_id == user_id]

    def by_id_for_user(self, task_id, user_id):
        task = self.tasks.get(task_id)
        return task if task and task.user_id == user_id else None

    def add(self, user_id, title, description):
        task = Task(
            len(self.tasks) + 1, user_id, title, description, False, datetime.now(timezone.utc)
        )
        self.tasks[task.id] = task
        return task

    def set_done(self, task_id, user_id, is_done):
        task = self.by_id_for_user(task_id, user_id)
        if task is None:
            return None
        updated = Task(task.id, task.user_id, task.title, task.description, is_done, task.created_at)
        self.tasks[task_id] = updated
        return updated

    def delete(self, task_id, user_id):
        if self.by_id_for_user(task_id, user_id) is None:
            return False
        del self.tasks[task_id]
        return True


class DomainTests(unittest.TestCase):
    def test_registration_and_login(self):
        service = AuthService(MemoryUsers(), FakeHasher(), FakeTokens())
        user = service.register("  Alice@Example.com  ", "password123")
        self.assertEqual(user.email, "alice@example.com")
        self.assertEqual(service.login("ALICE@example.com", "password123"), "token:1")
        with self.assertRaises(EmailAlreadyExists):
            service.register("alice@example.com", "password123")
        with self.assertRaises(InvalidCredentials):
            service.login("alice@example.com", "wrong")
        with self.assertRaises(InvalidInput):
            service.register("not-an-email", "password123")

    def test_task_ownership_and_validation(self):
        service = TaskService(MemoryTasks())
        task = service.create_task(1, "  Study  ", "  Chapter 1  ")
        self.assertEqual((task.title, task.description), ("Study", "Chapter 1"))
        self.assertEqual(service.set_done(1, task.id, True).is_done, True)
        with self.assertRaises(TaskNotFound):
            service.get_task(2, task.id)
        with self.assertRaises(TaskNotFound):
            service.delete_task(2, task.id)
        with self.assertRaises(InvalidInput):
            service.create_task(1, "  ", None)
        service.delete_task(1, task.id)
        self.assertEqual(service.list_tasks(1), [])


if __name__ == "__main__":
    unittest.main()
