from datetime import datetime, timedelta, timezone

import jwt
import pytest
from fastapi.testclient import TestClient

from app.factory import create_app


TEST_SECRET = "test-secret-with-at-least-thirty-two-characters"


def make_client(tmp_path):
    app = create_app(
        f"sqlite:///{(tmp_path / 'test.db').as_posix()}",
        TEST_SECRET,
    )
    return TestClient(app)


def register_and_login(client, email):
    registered = client.post(
        "/api/auth/register", json={"email": email, "password": "correct-horse-123"}
    )
    assert registered.status_code == 201
    assert set(registered.json()) == {"id", "email"}
    assert registered.json()["email"] == email.strip().lower()
    result = client.post(
        "/api/auth/login", json={"email": email, "password": "correct-horse-123"}
    )
    assert result.status_code == 200
    assert result.json()["token_type"] == "bearer"
    assert isinstance(result.json()["access_token"], str)
    return {"Authorization": f"Bearer {result.json()['access_token']}"}


def test_authentication_and_task_lifecycle(tmp_path):
    with make_client(tmp_path) as client:
        headers = register_and_login(client, "owner@example.com")
        assert client.get("/api/tasks", headers=headers).json() == []

        created = client.post(
            "/api/tasks", json={"title": "  Buy milk  ", "description": " Shop "}, headers=headers
        )
        assert created.status_code == 201
        task = created.json()
        token = headers["Authorization"].split(" ", 1)[1]
        claims = jwt.decode(token, TEST_SECRET, algorithms=["HS256"])
        assert task["user_id"] == int(claims["sub"])
        assert task["title"] == "Buy milk"
        assert task["description"] == "Shop"
        assert task["is_done"] is False
        assert task["created_at"].endswith("Z")

        task_id = task["id"]
        detail = client.get(f"/api/tasks/{task_id}", headers=headers)
        assert detail.status_code == 200
        assert detail.json() == task
        updated = client.patch(
            f"/api/tasks/{task_id}", json={"is_done": True}, headers=headers
        )
        assert updated.status_code == 200
        assert updated.json()["is_done"] is True
        assert client.get(f"/api/tasks/{task_id}", headers=headers).json()["is_done"] is True
        reopened = client.patch(
            f"/api/tasks/{task_id}", json={"is_done": False}, headers=headers
        )
        assert reopened.status_code == 200
        assert reopened.json() == task

        newer = client.post("/api/tasks", json={"title": "Second task"}, headers=headers)
        assert newer.status_code == 201
        listed = client.get("/api/tasks", headers=headers)
        assert listed.status_code == 200
        assert listed.json() == [newer.json(), task]
        deleted = client.delete(f"/api/tasks/{task_id}", headers=headers)
        assert deleted.status_code == 204
        assert deleted.content == b""
        missing = client.get(f"/api/tasks/{task_id}", headers=headers)
        assert missing.status_code == 404
        assert missing.json() == {"detail": "Task not found"}
        assert client.get("/api/tasks", headers=headers).json() == [newer.json()]


def test_owner_isolation_and_bad_credentials(tmp_path):
    with make_client(tmp_path) as client:
        owner = register_and_login(client, "owner@example.com")
        other = register_and_login(client, "other@example.com")
        created = client.post("/api/tasks", json={"title": "Private"}, headers=owner)
        assert created.status_code == 201
        task = created.json()
        task_id = task["id"]

        other_list = client.get("/api/tasks", headers=other)
        assert other_list.status_code == 200
        assert other_list.json() == []
        for method in ("GET", "PATCH", "DELETE"):
            kwargs = {"json": {"is_done": True}} if method == "PATCH" else {}
            denied = client.request(method, f"/api/tasks/{task_id}", headers=other, **kwargs)
            assert denied.status_code == 404, method
            assert denied.json() == {"detail": "Task not found"}, method
            unchanged = client.get(f"/api/tasks/{task_id}", headers=owner)
            assert unchanged.status_code == 200
            assert unchanged.json() == task, method
        assert client.get("/api/tasks", headers=owner).json() == [task]

        wrong_password = client.post(
            "/api/auth/login", json={"email": "owner@example.com", "password": "wrong"}
        )
        assert wrong_password.status_code == 401
        assert wrong_password.json() == {"detail": "Invalid email or password"}
        for duplicate_email in ("owner@example.com", "OWNER@example.com", "  owner@example.com  "):
            duplicate = client.post(
                "/api/auth/register", json={"email": duplicate_email, "password": "another-pass"}
            )
            assert duplicate.status_code == 409, duplicate_email
            assert duplicate.json() == {"detail": "Email already registered"}
        # A rejected duplicate must not replace the existing account/password.
        assert client.post(
            "/api/auth/login",
            json={"email": "owner@example.com", "password": "correct-horse-123"},
        ).status_code == 200


def test_openapi_marks_protected_operations(tmp_path):
    with make_client(tmp_path) as client:
        schema = client.get("/openapi.json").json()
        assert schema["paths"]["/api/tasks"]["get"]["security"] == [{"BearerAuth": []}]
        assert schema["paths"]["/api/tasks"]["post"]["security"] == [{"BearerAuth": []}]
        assert "security" not in schema["paths"]["/api/auth/login"]["post"]


def test_registration_normalizes_email_and_login_accepts_normalized_email(tmp_path):
    with make_client(tmp_path) as client:
        headers = register_and_login(client, "  Alice@Example.com  ")
        assert client.get("/api/tasks", headers=headers).status_code == 200
        result = client.post(
            "/api/auth/login",
            json={"email": "alice@example.com", "password": "correct-horse-123"},
        )
        assert result.status_code == 200
        assert result.json()["token_type"] == "bearer"
        unknown = client.post(
            "/api/auth/login",
            json={"email": "unknown@example.com", "password": "correct-horse-123"},
        )
        assert unknown.status_code == 401
        assert unknown.json() == {"detail": "Invalid email or password"}


@pytest.mark.parametrize(
    "body, expected_status, error_field",
    [
        pytest.param({"email": "not-an-email", "password": "password123"}, 400, None, id="invalid-email"),
        pytest.param({"email": "a@example.com", "password": "1234567"}, 422, "password", id="short-password"),
        pytest.param({"email": "a@example.com"}, 422, "password", id="missing-password"),
    ],
)
def test_registration_rejects_invalid_input(tmp_path, body, expected_status, error_field):
    with make_client(tmp_path) as client:
        response = client.post("/api/auth/register", json=body)
        assert response.status_code == expected_status
        if error_field:
            assert any(error["loc"] == ["body", error_field] for error in response.json()["detail"])
        else:
            assert isinstance(response.json()["detail"], str)


@pytest.mark.parametrize("method", ["GET", "POST"])
@pytest.mark.parametrize(
    "case", ["missing", "empty", "wrong-scheme", "malformed", "wrong-signature", "expired", "missing-exp"]
)
def test_tasks_reject_invalid_authentication(tmp_path, method, case):
    with make_client(tmp_path) as client:
        valid_headers = register_and_login(client, "owner@example.com")
        valid_token = valid_headers["Authorization"].split(" ", 1)[1]
        claims = jwt.decode(valid_token, TEST_SECRET, algorithms=["HS256"])
        if case == "missing":
            headers = {}
        elif case == "empty":
            headers = {"Authorization": "Bearer "}
        elif case == "wrong-scheme":
            headers = {"Authorization": f"Basic {valid_token}"}
        elif case == "malformed":
            headers = {"Authorization": "Bearer not-a-jwt"}
        else:
            secret = TEST_SECRET
            if case == "wrong-signature":
                secret = "different-test-secret-at-least-thirty-two-characters"
            elif case == "expired":
                now = datetime.now(timezone.utc)
                claims.update(iat=now - timedelta(hours=2), exp=now - timedelta(hours=1))
            elif case == "missing-exp":
                del claims["exp"]
            token = jwt.encode(claims, secret, algorithm="HS256")
            headers = {"Authorization": f"Bearer {token}"}
        kwargs = {"json": {"title": "Must not be created"}} if method == "POST" else {}
        response = client.request(method, "/api/tasks", headers=headers, **kwargs)
        assert response.status_code == 401
        assert response.headers["WWW-Authenticate"] == "Bearer"
        assert response.json() == {"detail": "Valid Bearer token required"}
        authorized = client.get("/api/tasks", headers=valid_headers)
        assert authorized.status_code == 200
        assert authorized.json() == []


@pytest.mark.parametrize(
    "body, expected_status",
    [
        pytest.param({}, 422, id="missing-title"),
        pytest.param({"title": None}, 422, id="null-title"),
        pytest.param({"title": ""}, 422, id="empty-title"),
        pytest.param({"title": " \t\n "}, 400, id="whitespace-title"),
        pytest.param({"title": "x" * 201}, 422, id="too-long-title"),
    ],
)
def test_task_rejects_invalid_title(tmp_path, body, expected_status):
    with make_client(tmp_path) as client:
        headers = register_and_login(client, "owner@example.com")
        response = client.post("/api/tasks", headers=headers, json=body)
        assert response.status_code == expected_status
        if expected_status == 400:
            assert response.json() == {"detail": "Title cannot be blank"}
        else:
            assert any(error["loc"] == ["body", "title"] for error in response.json()["detail"])
        assert client.get("/api/tasks", headers=headers).json() == []


def test_task_accepts_maximum_title_length_and_null_description(tmp_path):
    with make_client(tmp_path) as client:
        headers = register_and_login(client, "owner@example.com")
        response = client.post(
            "/api/tasks", headers=headers, json={"title": "x" * 200, "description": None}
        )
        assert response.status_code == 201
        task = response.json()
        assert task["title"] == "x" * 200
        assert task["description"] is None
        assert client.get(f"/api/tasks/{task['id']}", headers=headers).json() == task


@pytest.mark.parametrize("method", ["GET", "PATCH", "DELETE"])
def test_nonexistent_task_returns_not_found(tmp_path, method):
    with make_client(tmp_path) as client:
        headers = register_and_login(client, "owner@example.com")
        kwargs = {"json": {"is_done": True}} if method == "PATCH" else {}
        response = client.request(method, "/api/tasks/999", headers=headers, **kwargs)
        assert response.status_code == 404
        assert response.json() == {"detail": "Task not found"}


@pytest.mark.parametrize("body", [{}, {"is_done": None}, {"is_done": "not-a-boolean"}])
def test_invalid_status_update_does_not_change_task(tmp_path, body):
    with make_client(tmp_path) as client:
        headers = register_and_login(client, "owner@example.com")
        created = client.post("/api/tasks", headers=headers, json={"title": "Keep unchanged"})
        assert created.status_code == 201
        task = created.json()
        response = client.patch(f"/api/tasks/{task['id']}", headers=headers, json=body)
        assert response.status_code == 422
        assert any(error["loc"] == ["body", "is_done"] for error in response.json()["detail"])
        assert client.get(f"/api/tasks/{task['id']}", headers=headers).json() == task
