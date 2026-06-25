"""这个文件用于验证专利审查任务接口的上传校验和权限隔离。"""

from io import BytesIO

from docx import Document
from fastapi import UploadFile
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session
from starlette.datastructures import Headers

from app.core.config import get_settings
from app.core.security import hash_password
from app.db.base import Base
from app.db.session import SessionLocal, engine
from app.main import create_app
from app.models.model_call_log import ModelCallLog
from app.models.patent_check_task import PatentCheckTask
from app.models.user import User
from app.services.patent_check_service import create_patent_check_task
from app.worker import call_and_log, normalize_final_report, run_patent_check_task


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


def real_docx_file(name: str, *paragraphs: str) -> tuple[str, bytes, str]:
    document = Document()
    for paragraph in paragraphs:
        document.add_paragraph(paragraph)
    buffer = BytesIO()
    document.save(buffer)
    return (
        name,
        buffer.getvalue(),
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )


def upload_file(
    filename: str,
    content: bytes = b"%PDF-1.4 fake content",
    content_type: str = "application/pdf",
) -> UploadFile:
    return UploadFile(
        file=BytesIO(content),
        filename=filename,
        headers=Headers({"content-type": content_type}),
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


def test_create_task_ignores_empty_optional_file_inputs_from_browser(
    monkeypatch, client: TestClient
) -> None:
    monkeypatch.setattr(
        "app.services.patent_check_service.extract_document_text",
        lambda path: f"抽取文本 {path.name}",
    )
    login(client)

    response = client.post(
        "/api/patent-checks",
        data={"title": "浏览器空可选文件字段任务"},
        files={
            "claims": pdf_file("claims.pdf"),
            "specification": pdf_file("specification.pdf"),
            "drawings": ("", b"", "application/octet-stream"),
            "abstract": ("", b"", "application/octet-stream"),
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["drawings_text_length"] == 0
    assert payload["abstract_text_length"] == 0
    assert len(payload["files"]) == 2


def test_create_task_service_ignores_browser_empty_optional_uploads(
    monkeypatch, db_session: Session
) -> None:
    monkeypatch.setattr(
        "app.services.patent_check_service.extract_document_text",
        lambda path: f"抽取文本 {path.name}",
    )
    user = db_session.scalar(select(User).where(User.username == "alice"))
    assert user is not None

    task = create_patent_check_task(
        db=db_session,
        settings=get_settings(),
        user=user,
        title="服务层空可选文件字段任务",
        technical_field=None,
        uploads={
            "claims": upload_file("claims.pdf"),
            "specification": upload_file("specification.pdf"),
            "drawings": upload_file("", b"", "application/octet-stream"),
            "abstract": upload_file("", b"", "application/octet-stream"),
        },
    )

    assert task.drawings_text_length == 0
    assert task.abstract_text_length == 0
    assert len(task.files) == 2


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


def test_get_task_returns_progress_fields(client: TestClient, db_session: Session) -> None:
    alice = db_session.scalar(select(User).where(User.username == "alice"))
    assert alice is not None
    task = PatentCheckTask(
        user_id=alice.id,
        title="进度展示任务",
        status="running",
        progress_stage="stage_one",
        progress_percent=40,
        progress_message="正在审查权利要求书。",
    )
    db_session.add(task)
    db_session.commit()
    login(client, "alice")

    response = client.get(f"/api/patent-checks/{task.id}")

    assert response.status_code == 200
    payload = response.json()
    assert payload["progress_stage"] == "stage_one"
    assert payload["progress_percent"] == 40
    assert payload["progress_message"] == "正在审查权利要求书。"
    assert payload["progress_steps"][2] == {
        "key": "stage_one",
        "label": "第一阶段：权利要求书检查",
        "status": "running",
    }


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


def test_normalize_final_report_keeps_stage_one_when_stage_two_has_title() -> None:
    report = normalize_final_report(
        "### 第一阶段发现\n- 权利要求缺少必要技术特征。",
        "# 专利文件检查报告\n\n### 第二阶段发现\n- 说明书支持不足。",
    )

    assert report.startswith("# 专利文件检查报告")
    assert "## 第一阶段：权利要求书检查与特征分解" in report
    assert "权利要求缺少必要技术特征" in report
    assert "## 第二阶段：说明书检查" in report
    assert "说明书支持不足" in report


def test_failed_worker_task_can_be_retried_after_real_docx_upload(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("UPLOAD_DIR", str(tmp_path))
    monkeypatch.setenv("ENABLE_WORKER_QUEUE", "false")
    monkeypatch.setenv("GPT_API_KEY", "")
    get_settings.cache_clear()
    try:
        Base.metadata.drop_all(bind=engine)
        Base.metadata.create_all(bind=engine)
        with SessionLocal() as db:
            db.add(User(username="alice", password_hash=hash_password("password123"), role="user"))
            db.commit()

        app = create_app()
        with TestClient(app) as integration_client:
            login(integration_client)
            create_response = integration_client.post(
                "/api/patent-checks",
                data={"title": "真实 Word 集成任务", "technical_field": "人工智能"},
                files={
                    "claims": real_docx_file("claims.docx", "权利要求1：一种数据处理方法。"),
                    "specification": real_docx_file(
                        "specification.docx",
                        "说明书充分解释数据处理方法的输入、处理和输出。",
                    ),
                },
            )
            assert create_response.status_code == 200
            task_id = create_response.json()["id"]

            run_patent_check_task(task_id)

            retry_response = integration_client.post(f"/api/patent-checks/{task_id}/retry")

        assert retry_response.status_code == 200
        assert retry_response.json()["status"] == "pending"
    finally:
        get_settings.cache_clear()


def test_call_and_log_records_unexpected_model_exceptions(db_session: Session) -> None:
    class BrokenClient:
        settings = type("SettingsStub", (), {"gpt_model": "test-model"})()

        def chat(self, messages):
            raise RuntimeError("transport exploded")

    alice = db_session.scalar(select(User).where(User.username == "alice"))
    assert alice is not None
    task = PatentCheckTask(user_id=alice.id, title="异常审计任务")
    db_session.add(task)
    db_session.commit()

    try:
        call_and_log(
            db=db_session,
            task=task,
            client=BrokenClient(),
            stage="stage_two",
            messages=[{"role": "user", "content": "不会写入日志的完整文本"}],
        )
    except RuntimeError:
        pass

    log = db_session.scalar(select(ModelCallLog).where(ModelCallLog.task_id == task.id))
    assert log is not None
    assert log.status == "failed"
    assert log.stage == "stage_two"
    assert "RuntimeError" in (log.error_message or "")
    assert "不会写入日志的完整文本" not in (log.error_message or "")
