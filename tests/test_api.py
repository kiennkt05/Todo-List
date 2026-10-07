from fastapi.testclient import TestClient

from app.factory import create_app


def make_client(tmp_path):
    app = create_app(
        f"sqlite:///{(tmp_path / 'test.db').as_posix()}",
        "test-secret-with-at-least-thirty-two-characters",
    )
    return TestClient(app)


def register_and_login(client, email):
    assert client.post(
        "/api/auth/register", json={"email": email, "password": "correct-horse-123"}
    ).status_code == 201
    result = client.post(
        "/api/auth/login", json={"email": email, "password": "correct-horse-123"}
    )
    assert result.status_code == 200
    return {"Authorization": f"Bearer {result.json()['access_token']}"}


def test_authentication_and_task_lifecycle(tmp_path):
    with make_client(tmp_path) as client:
        assert client.get("/api/tasks").status_code == 401
        assert client.post("/api/tasks", json={"title": "Buy milk"}).status_code == 401
        headers = register_and_login(client, "owner@example.com")
        assert client.get("/api/tasks", headers=headers).json() == []

        created = client.post(
            "/api/tasks", json={"title": "  Buy milk  ", "description": " Shop "}, headers=headers
        )
        assert created.status_code == 201
        task = created.json()
        assert task["title"] == "Buy milk"
        assert task["description"] == "Shop"
        assert task["is_done"] is False
        assert task["created_at"].endswith("Z")

        task_id = task["id"]
        assert client.get(f"/api/tasks/{task_id}", headers=headers).status_code == 200
        updated = client.patch(
            f"/api/tasks/{task_id}", json={"is_done": True}, headers=headers
        )
        assert updated.status_code == 200
        assert updated.json()["is_done"] is True
        assert [item["id"] for item in client.get("/api/tasks", headers=headers).json()] == [task_id]
        assert client.delete(f"/api/tasks/{task_id}", headers=headers).status_code == 204
        assert client.get(f"/api/tasks/{task_id}", headers=headers).status_code == 404


def test_owner_isolation_and_bad_credentials(tmp_path):
    with make_client(tmp_path) as client:
        owner = register_and_login(client, "owner@example.com")
        other = register_and_login(client, "other@example.com")
        task_id = client.post("/api/tasks", json={"title": "Private"}, headers=owner).json()["id"]

        assert client.get("/api/tasks", headers=other).json() == []
        assert client.get(f"/api/tasks/{task_id}", headers=other).status_code == 404
        assert client.patch(
            f"/api/tasks/{task_id}", json={"is_done": True}, headers=other
        ).status_code == 404
        assert client.delete(f"/api/tasks/{task_id}", headers=other).status_code == 404
        assert client.get(f"/api/tasks/{task_id}", headers=owner).json()["is_done"] is False

        assert client.post(
            "/api/auth/login", json={"email": "owner@example.com", "password": "wrong"}
        ).status_code == 401
        assert client.get(
            "/api/tasks", headers={"Authorization": "Bearer invalid"}
        ).status_code == 401
        assert client.post(
            "/api/auth/register", json={"email": "OWNER@example.com", "password": "another-pass"}
        ).status_code == 409


def test_openapi_marks_protected_operations(tmp_path):
    with make_client(tmp_path) as client:
        schema = client.get("/openapi.json").json()
        assert schema["paths"]["/api/tasks"]["get"]["security"] == [{"BearerAuth": []}]
        assert schema["paths"]["/api/tasks"]["post"]["security"] == [{"BearerAuth": []}]
        assert "security" not in schema["paths"]["/api/auth/login"]["post"]
