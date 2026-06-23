"""这个文件用于验证密码哈希不会明文存储且可正确校验。"""

from app.core.security import hash_password, verify_password


def test_password_hash_does_not_store_plaintext() -> None:
    password_hash = hash_password("password123")

    assert password_hash != "password123"
    assert "password123" not in password_hash


def test_password_verify_accepts_correct_password() -> None:
    password_hash = hash_password("password123")

    assert verify_password("password123", password_hash) is True
    assert verify_password("wrong", password_hash) is False
