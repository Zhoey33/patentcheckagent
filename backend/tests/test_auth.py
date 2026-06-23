"""这个文件用于验证登录、登出和当前用户接口行为。"""

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.user import User


def test_login_success_sets_cookie(client: TestClient) -> None:
    response = client.post("/api/auth/login", json={"username": "alice", "password": "password123"})

    assert response.status_code == 200
    assert response.json()["username"] == "alice"
    assert "access_token" in response.cookies


def test_login_failure_uses_generic_message(client: TestClient) -> None:
    response = client.post("/api/auth/login", json={"username": "alice", "password": "wrong"})

    assert response.status_code == 401
    assert response.json()["detail"] == "账号或密码错误。"


def test_disabled_user_cannot_login(client: TestClient, db_session: Session) -> None:
    user = db_session.scalar(select(User).where(User.username == "alice"))
    assert user is not None
    user.is_active = False
    db_session.commit()

    response = client.post("/api/auth/login", json={"username": "alice", "password": "password123"})

    assert response.status_code == 401


def test_me_requires_login(client: TestClient) -> None:
    response = client.get("/api/auth/me")

    assert response.status_code == 401


def test_me_returns_current_user(client: TestClient) -> None:
    client.post("/api/auth/login", json={"username": "alice", "password": "password123"})

    response = client.get("/api/auth/me")

    assert response.status_code == 200
    assert response.json()["username"] == "alice"
