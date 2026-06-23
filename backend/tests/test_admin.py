"""这个文件用于验证管理员接口的账号维护和全量任务查看能力。"""

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import verify_password
from app.models.patent_check_task import PatentCheckTask
from app.models.user import User


def login(client: TestClient, username: str = "admin", password: str = "password123") -> None:
    response = client.post(
        "/api/auth/login",
        json={"username": username, "password": password},
    )
    assert response.status_code == 200


def test_regular_user_cannot_access_admin_users(client: TestClient) -> None:
    login(client, "alice")

    response = client.get("/api/admin/users")

    assert response.status_code == 403


def test_admin_can_list_users(client: TestClient) -> None:
    login(client)

    response = client.get("/api/admin/users")

    assert response.status_code == 200
    usernames = {item["username"] for item in response.json()["items"]}
    assert {"alice", "bob", "admin"}.issubset(usernames)


def test_admin_can_create_user(client: TestClient, db_session: Session) -> None:
    login(client)

    response = client.post(
        "/api/admin/users",
        json={
            "username": "new_user",
            "password": "SecurePassword123!",
            "role": "user",
            "is_active": True,
        },
    )

    assert response.status_code == 200
    assert response.json()["username"] == "new_user"
    created = db_session.scalar(select(User).where(User.username == "new_user"))
    assert created is not None
    assert created.password_hash != "SecurePassword123!"
    assert verify_password("SecurePassword123!", created.password_hash)


def test_admin_create_user_rejects_duplicate_username(client: TestClient) -> None:
    login(client)

    response = client.post(
        "/api/admin/users",
        json={
            "username": "alice",
            "password": "SecurePassword123!",
            "role": "user",
            "is_active": True,
        },
    )

    assert response.status_code == 400
    assert "已存在" in response.json()["detail"]


def test_admin_can_disable_user(client: TestClient, db_session: Session) -> None:
    login(client)
    user = db_session.scalar(select(User).where(User.username == "alice"))
    assert user is not None

    response = client.patch(f"/api/admin/users/{user.id}", json={"is_active": False})

    assert response.status_code == 200
    db_session.refresh(user)
    assert user.is_active is False


def test_admin_can_reset_password(client: TestClient, db_session: Session) -> None:
    login(client)
    user = db_session.scalar(select(User).where(User.username == "alice"))
    assert user is not None
    old_hash = user.password_hash

    response = client.post(
        f"/api/admin/users/{user.id}/reset-password",
        json={"password": "NewPassword123!"},
    )

    assert response.status_code == 200
    db_session.refresh(user)
    assert user.password_hash != old_hash
    assert verify_password("NewPassword123!", user.password_hash)


def test_admin_can_view_all_tasks(client: TestClient, db_session: Session) -> None:
    alice = db_session.scalar(select(User).where(User.username == "alice"))
    bob = db_session.scalar(select(User).where(User.username == "bob"))
    assert alice is not None
    assert bob is not None
    db_session.add(PatentCheckTask(user_id=alice.id, title="alice 任务"))
    db_session.add(PatentCheckTask(user_id=bob.id, title="bob 任务"))
    db_session.commit()
    login(client)

    response = client.get("/api/admin/patent-checks")

    assert response.status_code == 200
    titles = {item["title"] for item in response.json()["items"]}
    assert {"alice 任务", "bob 任务"}.issubset(titles)
