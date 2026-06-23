"""这个文件用于从环境变量幂等创建首批内部账号。"""

import os

from sqlalchemy import select

from app.core.security import hash_password
from app.db.base import Base
from app.db.session import SessionLocal, engine
from app.models.user import User


def upsert_user(username: str, password: str, role: str) -> None:
    """Create a user if missing, otherwise update password and role."""

    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.username == username))
        if user is None:
            user = User(username=username, password_hash=hash_password(password), role=role)
            db.add(user)
        else:
            user.password_hash = hash_password(password)
            user.role = role
            user.is_active = True
        db.commit()


def main() -> None:
    """Seed one admin and two regular internal users."""

    Base.metadata.create_all(bind=engine)
    upsert_user(
        os.getenv("SEED_ADMIN_USERNAME", "admin"),
        os.getenv("SEED_ADMIN_PASSWORD", "ChangeMeAdmin123!"),
        "admin",
    )
    upsert_user(
        os.getenv("SEED_USER1_USERNAME", "researcher1"),
        os.getenv("SEED_USER1_PASSWORD", "ChangeMeUser123!"),
        "user",
    )
    upsert_user(
        os.getenv("SEED_USER2_USERNAME", "researcher2"),
        os.getenv("SEED_USER2_PASSWORD", "ChangeMeUser123!"),
        "user",
    )


if __name__ == "__main__":
    main()
