"""这个文件用于提供后端测试共享的数据库和客户端夹具。"""

import os
import tempfile
from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

os.environ["APP_ENV"] = "test"
os.environ["APP_SECRET_KEY"] = "test-secret-key-with-at-least-32-bytes"
os.environ["DATABASE_URL"] = "sqlite:///./test_patent_check_agent.sqlite3"
os.environ["ENABLE_WORKER_QUEUE"] = "false"

from app.core.config import get_settings  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.db.base import Base  # noqa: E402
from app.db.session import get_db  # noqa: E402
from app.main import create_app  # noqa: E402
from app.models.user import User  # noqa: E402


@pytest.fixture()
def db_session() -> Generator[Session, None, None]:
    with tempfile.TemporaryDirectory() as tmpdir:
        os.environ["UPLOAD_DIR"] = tmpdir
        get_settings.cache_clear()
        engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
        Base.metadata.create_all(bind=engine)
        db = TestingSessionLocal()
        try:
            db.add(User(username="alice", password_hash=hash_password("password123"), role="user"))
            db.add(User(username="bob", password_hash=hash_password("password123"), role="user"))
            db.add(User(username="admin", password_hash=hash_password("password123"), role="admin"))
            db.commit()
            yield db
        finally:
            db.close()


@pytest.fixture()
def client(db_session: Session) -> Generator[TestClient, None, None]:
    app = create_app()

    def override_get_db() -> Generator[Session, None, None]:
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
