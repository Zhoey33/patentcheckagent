"""这个文件用于验证专利审查任务接口的上传校验和权限隔离。"""

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.patent_check_task import PatentCheckTask
from app.models.user import User


def login(client: TestClient, username: str = "alice") -> None:
    response = client.post(
        "/api/auth/login",
        json={"username": username, "password": "password123"},
    )
    assert response.status_code == 200


def pdf_file(name: str) -> tuple[str, bytes, str]:
    return (name, b"%PDF-1.4 fake content", "application/pdf")


def docx_file(name: str) -> tuple[str, bytes, str]:
    return (
        name,
        b"fake docx content",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )


def test_create_task_requires_login(client: TestClient) -> None:
    response = client.get("/api/patent-checks")

    assert response.status_code == 401


def test_create_task_rejects_non_pdf(client: TestClient) -> None:
    login(client)

    response = client.post(
        "/api/patent-checks",
        data={"title": "测试任务"},
        files={
            "claims": ("claims.txt", b"hello", "text/plain"),
            "specification": pdf_file("specification.pdf"),
            "drawings": pdf_file("drawings.pdf"),
        },
    )

    assert response.status_code == 400
    assert "PDF 或 Word" in response.json()["detail"]


def test_create_task_saves_metadata(monkeypatch, client: TestClient) -> None:
    monkeypatch.setattr(
        "app.services.patent_check_service.extract_document_text",
        lambda path: f"抽取文本 {path.name}",
    )
    login(client)

    response = client.post(
        "/api/patent-checks",
        data={"title": "测试任务", "technical_field": "人工智能"},
        files={
            "claims": pdf_file("claims.pdf"),
            "specification": pdf_file("specification.pdf"),
            "drawings": pdf_file("drawings.pdf"),
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["title"] == "测试任务"
    assert payload["technical_field"] == "人工智能"
    assert payload["status"] == "pending"
    assert len(payload["files"]) == 3


def test_create_task_accepts_docx_uploads(monkeypatch, client: TestClient) -> None:
    monkeypatch.setattr(
        "app.services.patent_check_service.extract_document_text",
        lambda path: f"抽取文本 {path.name}",
    )
    login(client)

    response = client.post(
        "/api/patent-checks",
        data={"title": "Word 格式任务"},
        files={
            "claims": docx_file("claims.docx"),
            "specification": docx_file("specification.docx"),
            "drawings": docx_file("drawings.docx"),
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["title"] == "Word 格式任务"
    assert len(payload["files"]) == 3


def test_create_task_treats_drawings_as_optional(monkeypatch, client: TestClient) -> None:
    monkeypatch.setattr(
        "app.services.patent_check_service.extract_document_text",
        lambda path: f"抽取文本 {path.name}",
    )
    login(client)

    response = client.post(
        "/api/patent-checks",
        data={"title": "无附图说明任务"},
        files={
            "claims": pdf_file("claims.pdf"),
            "specification": pdf_file("specification.pdf"),
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["drawings_text_length"] == 0
    assert len(payload["files"]) == 2


def test_regular_user_cannot_read_other_users_task(
    client: TestClient, db_session: Session
) -> None:
    alice = db_session.scalar(select(User).where(User.username == "alice"))
    assert alice is not None
    task = PatentCheckTask(user_id=alice.id, title="alice 的任务")
    db_session.add(task)
    db_session.commit()
    login(client, "bob")

    response = client.get(f"/api/patent-checks/{task.id}")

    assert response.status_code == 404


def test_retry_failed_task_requires_available_process_text(
    client: TestClient, db_session: Session
) -> None:
    alice = db_session.scalar(select(User).where(User.username == "alice"))
    assert alice is not None
    task = PatentCheckTask(
        user_id=alice.id,
        title="已清理的失败任务",
        status="failed",
        process_text_path=None,
        input_cleanup_status="cleaned",
        error_message="模型调用失败。",
    )
    db_session.add(task)
    db_session.commit()
    login(client, "alice")

    response = client.post(f"/api/patent-checks/{task.id}/retry")

    assert response.status_code == 400
    assert "重新提交文件" in response.json()["detail"]
