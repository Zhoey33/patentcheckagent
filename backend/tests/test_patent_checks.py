"""这个文件用于验证专利审查任务接口的上传校验和权限隔离。"""

from datetime import UTC, datetime, timedelta
from io import BytesIO

from docx import Document
from fastapi import UploadFile
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session
from starlette.datastructures import Headers

from app.api.patent_checks import build_task_status_payload
from app.core.config import Settings, get_settings
from app.core.security import hash_password
from app.db.base import Base
from app.db.session import SessionLocal, engine
from app.main import create_app
from app.models.model_call_log import ModelCallLog
from app.models.patent_check_event import PatentCheckEvent
from app.models.patent_check_file import PatentCheckFile
from app.models.patent_check_task import PatentCheckTask
from app.models.user import User
from app.scripts.recover_stale_tasks import recover_stale_running_tasks
from app.services.codex_client import CodexEvent, CodexRunResult
from app.services.errors import UserFacingError
from app.services.patent_check_service import create_patent_check_task
from app.worker import (
    call_and_log,
    normalize_final_report,
    persist_codex_event,
    run_patent_check_task,
)


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


def test_create_task_accepts_visual_only_drawings_upload(
    monkeypatch, client: TestClient
) -> None:
    def fake_extract(path):
        if path.name.startswith("drawings-"):
            raise UserFacingError("未能抽取到可复制文本，请上传可复制文本型 PDF。")
        return f"抽取文本 {path.name}"

    monkeypatch.setattr("app.services.patent_check_service.extract_document_text", fake_extract)
    login(client)

    response = client.post(
        "/api/patent-checks",
        data={"title": "图片附图任务"},
        files={
            "claims": pdf_file("claims.pdf"),
            "specification": pdf_file("specification.pdf"),
            "drawings": pdf_file("drawings.pdf"),
        },
    )

    assert response.status_code == 200
    payload = response.json()
    drawing_file = next(file for file in payload["files"] if file["file_role"] == "drawings")
    assert payload["drawings_text_length"] == 0
    assert drawing_file["extraction_status"] == "text_unavailable"
    assert "未能抽取到" in drawing_file["extraction_error"]


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


def test_get_task_events_returns_codex_execution_history(
    client: TestClient, db_session: Session
) -> None:
    alice = db_session.scalar(select(User).where(User.username == "alice"))
    assert alice is not None
    task = PatentCheckTask(user_id=alice.id, title="Codex 事件任务")
    db_session.add(task)
    db_session.flush()
    db_session.add(
        PatentCheckEvent(
            task_id=task.id,
            stage="stage_one",
            event_type="thread.started",
            message="Codex 会话已启动。",
            raw_payload='{"type":"thread.started","thread_id":"thread-1"}',
        )
    )
    db_session.add(
        PatentCheckEvent(
            task_id=task.id,
            stage="stage_one",
            event_type="event_msg",
            message="第一阶段正在分析权利要求。",
            raw_payload='{"type":"event_msg","payload":{"type":"agent_message"}}',
        )
    )
    db_session.commit()
    login(client, "alice")

    response = client.get(f"/api/patent-checks/{task.id}/events")

    assert response.status_code == 200
    payload = response.json()
    assert [event["message"] for event in payload["items"]] == [
        "Codex 会话已启动。",
        "第一阶段正在分析权利要求。",
    ]
    assert payload["items"][0]["stage"] == "stage_one"
    assert payload["items"][0]["event_type"] == "thread.started"


def test_stream_task_events_returns_sse_frames(client: TestClient, db_session: Session) -> None:
    alice = db_session.scalar(select(User).where(User.username == "alice"))
    assert alice is not None
    task = PatentCheckTask(
        user_id=alice.id,
        title="Codex SSE 任务",
        status="succeeded",
        progress_stage="completed",
        progress_percent=100,
        progress_message="审查完成，报告已生成。",
    )
    db_session.add(task)
    db_session.flush()
    db_session.add(
        PatentCheckEvent(
            task_id=task.id,
            stage="stage_one",
            event_type="thread.started",
            message="Codex 会话已启动。",
            raw_payload='{"type":"thread.started","thread_id":"thread-1"}',
        )
    )
    db_session.commit()
    login(client, "alice")

    with client.stream("GET", f"/api/patent-checks/{task.id}/events/stream") as response:
        body = response.read().decode("utf-8")

    assert response.status_code == 200
    assert "event: codex_event" in body
    assert "Codex 会话已启动。" in body
    assert "event: task_status" in body
    assert '"status": "succeeded"' in body


def test_stream_task_events_includes_report_snapshot_content(
    client: TestClient, db_session: Session
) -> None:
    alice = db_session.scalar(select(User).where(User.username == "alice"))
    assert alice is not None
    task = PatentCheckTask(
        user_id=alice.id,
        title="Codex 报告流任务",
        status="succeeded",
        progress_stage="completed",
        progress_percent=100,
        progress_message="审查完成，报告已生成。",
    )
    db_session.add(task)
    db_session.flush()
    db_session.add(
        PatentCheckEvent(
            task_id=task.id,
            stage="stage_one",
            event_type="report_snapshot",
            message="第一阶段报告内容已更新。",
            raw_payload='{"type":"report_snapshot","content":"### 审查结论\\n- 存在问题"}',
        )
    )
    db_session.commit()
    login(client, "alice")

    events_response = client.get(f"/api/patent-checks/{task.id}/events")
    with client.stream("GET", f"/api/patent-checks/{task.id}/events/stream") as stream_response:
        body = stream_response.read().decode("utf-8")

    assert events_response.status_code == 200
    assert events_response.json()["items"][0]["content"] == "### 审查结论\n- 存在问题"
    assert stream_response.status_code == 200
    assert "event: report_snapshot" in body
    assert '"content": "### 审查结论\\n- 存在问题"' in body


def test_task_status_payload_includes_progress_steps(db_session: Session) -> None:
    alice = db_session.scalar(select(User).where(User.username == "alice"))
    assert alice is not None
    task = PatentCheckTask(
        user_id=alice.id,
        title="状态同步任务",
        status="running",
        progress_stage="stage_two",
        progress_percent=75,
        progress_message="正在核对说明书。",
    )
    db_session.add(task)
    db_session.commit()

    payload = build_task_status_payload(task)

    assert payload["status"] == "running"
    assert payload["progress_percent"] == 75
    assert payload["progress_steps"][3] == {
        "key": "stage_two",
        "label": "第二阶段：说明书/附图/摘要检查",
        "status": "running",
    }


def test_cancel_pending_task_marks_cancelled_and_cleans_inputs(
    tmp_path, client: TestClient, db_session: Session
) -> None:
    process_text_path = tmp_path / "task-input.json"
    upload_path = tmp_path / "claims.pdf"
    process_text_path.write_text('{"claims":"权利要求","specification":"说明书"}', encoding="utf-8")
    upload_path.write_bytes(b"%PDF-1.4 fake content")
    alice = db_session.scalar(select(User).where(User.username == "alice"))
    assert alice is not None
    task = PatentCheckTask(
        user_id=alice.id,
        title="可取消任务",
        status="pending",
        process_text_path=str(process_text_path),
        progress_stage="queued",
        progress_percent=5,
        progress_message="任务已提交，等待审查队列调度。",
    )
    db_session.add(task)
    db_session.flush()
    db_session.add(
        PatentCheckFile(
            task_id=task.id,
            file_role="claims",
            original_filename="claims.pdf",
            stored_path=str(upload_path),
            content_type="application/pdf",
            file_size_bytes=upload_path.stat().st_size,
            extracted_text_length=10,
            extraction_status="succeeded",
        )
    )
    db_session.commit()
    login(client, "alice")

    response = client.post(f"/api/patent-checks/{task.id}/cancel")

    assert response.status_code == 200
    payload = response.json()
    db_session.refresh(task)
    assert payload["status"] == "cancelled"
    assert payload["progress_message"] == "用户已取消审查。"
    assert task.input_cleanup_status == "cleaned"
    assert task.process_text_path is None
    assert not process_text_path.exists()
    assert not upload_path.exists()
    assert task.files[0].stored_path is None


def test_cancel_running_task_keeps_inputs_for_worker_cleanup(
    tmp_path, client: TestClient, db_session: Session
) -> None:
    process_text_path = tmp_path / "task-input.json"
    upload_path = tmp_path / "claims.pdf"
    process_text_path.write_text('{"claims":"权利要求","specification":"说明书"}', encoding="utf-8")
    upload_path.write_bytes(b"%PDF-1.4 fake content")
    alice = db_session.scalar(select(User).where(User.username == "alice"))
    assert alice is not None
    task = PatentCheckTask(
        user_id=alice.id,
        title="运行中取消任务",
        status="running",
        process_text_path=str(process_text_path),
        progress_stage="stage_one",
        progress_percent=40,
        progress_message="正在执行第一阶段。",
    )
    db_session.add(task)
    db_session.flush()
    db_session.add(
        PatentCheckFile(
            task_id=task.id,
            file_role="claims",
            original_filename="claims.pdf",
            stored_path=str(upload_path),
            content_type="application/pdf",
            file_size_bytes=upload_path.stat().st_size,
            extracted_text_length=10,
            extraction_status="succeeded",
        )
    )
    db_session.commit()
    login(client, "alice")

    response = client.post(f"/api/patent-checks/{task.id}/cancel")

    assert response.status_code == 200
    payload = response.json()
    db_session.refresh(task)
    assert payload["status"] == "cancelled"
    assert task.input_cleanup_status == "pending"
    assert task.process_text_path == str(process_text_path)
    assert process_text_path.exists()
    assert upload_path.exists()
    assert task.files[0].stored_path == str(upload_path)


def test_persist_codex_event_does_not_overwrite_cancelled_progress(
    db_session: Session,
) -> None:
    alice = db_session.scalar(select(User).where(User.username == "alice"))
    assert alice is not None
    task = PatentCheckTask(
        user_id=alice.id,
        title="已取消事件任务",
        status="cancelled",
        progress_stage="stage_one",
        progress_percent=40,
        progress_message="用户已取消审查。",
    )
    db_session.add(task)
    db_session.commit()

    persist_codex_event(
        db_session,
        task,
        CodexEvent(
            stage="stage_one",
            event_type="turn.completed",
            message="第一阶段检查完成，准备核对说明书支持情况。",
            raw_payload={"type": "turn.completed"},
        ),
    )

    db_session.refresh(task)
    assert task.progress_message == "用户已取消审查。"


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


def test_retry_failed_task_clears_stale_outputs_and_events(
    tmp_path, client: TestClient, db_session: Session
) -> None:
    process_text_path = tmp_path / "task-input.json"
    process_text_path.write_text(
        '{"claims":"权利要求文本","specification":"说明书文本"}',
        encoding="utf-8",
    )
    alice = db_session.scalar(select(User).where(User.username == "alice"))
    assert alice is not None
    task = PatentCheckTask(
        user_id=alice.id,
        title="带旧结果的失败任务",
        status="failed",
        process_text_path=str(process_text_path),
        input_cleanup_status="retryable",
        progress_stage="stage_two",
        progress_percent=75,
        progress_message="上一轮失败。",
        stage_one_result="上一轮第一阶段结果",
        final_report="# 上一轮报告",
        error_message="上一轮错误。",
    )
    db_session.add(task)
    db_session.flush()
    db_session.add(
        PatentCheckEvent(
            task_id=task.id,
            stage="stage_one",
            event_type="event_msg",
            message="上一轮 Codex 事件。",
            raw_payload='{"type":"event_msg"}',
        )
    )
    db_session.commit()
    login(client, "alice")

    response = client.post(f"/api/patent-checks/{task.id}/retry")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "pending"
    refreshed_task = db_session.get(PatentCheckTask, task.id)
    assert refreshed_task is not None
    assert refreshed_task.stage_one_result is None
    assert refreshed_task.final_report is None
    assert refreshed_task.error_message is None
    remaining_event = db_session.scalar(
        select(PatentCheckEvent).where(PatentCheckEvent.task_id == task.id)
    )
    assert remaining_event is None


def test_recover_stale_running_tasks_marks_only_expired_tasks_retryable(
    tmp_path, db_session: Session
) -> None:
    now = datetime(2026, 7, 4, 3, 20, tzinfo=UTC)
    stale_input = tmp_path / "stale-input.json"
    stale_input.write_text('{"claims":"权利要求","specification":"说明书"}', encoding="utf-8")
    fresh_input = tmp_path / "fresh-input.json"
    fresh_input.write_text('{"claims":"权利要求","specification":"说明书"}', encoding="utf-8")
    alice = db_session.scalar(select(User).where(User.username == "alice"))
    assert alice is not None
    stale_task = PatentCheckTask(
        user_id=alice.id,
        title="过期运行任务",
        status="running",
        progress_stage="stage_one",
        progress_percent=40,
        progress_message="正在执行第一阶段。",
        process_text_path=str(stale_input),
        started_at=now - timedelta(seconds=400),
    )
    fresh_task = PatentCheckTask(
        user_id=alice.id,
        title="近期运行任务",
        status="running",
        progress_stage="stage_one",
        progress_percent=40,
        progress_message="正在执行第一阶段。",
        process_text_path=str(fresh_input),
        started_at=now - timedelta(seconds=120),
    )
    db_session.add_all([stale_task, fresh_task])
    db_session.commit()

    recovered = recover_stale_running_tasks(
        db_session,
        settings=Settings(app_secret_key="test-secret-key-with-at-least-32-bytes"),
        now=now,
    )

    assert recovered == 1
    assert stale_task.status == "failed"
    assert stale_task.input_cleanup_status == "retryable"
    assert stale_task.finished_at == now.replace(tzinfo=None)
    assert "可点击重试" in (stale_task.error_message or "")
    assert fresh_task.status == "running"


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


def test_normalize_final_report_removes_duplicate_stage_titles_and_adds_body_headings() -> None:
    report = normalize_final_report(
        "\n".join(
            [
                "## 第一阶段：权利要求书检查与特征分解",
                "## 第一阶段：权利要求书检查与特征分解",
                "- 权利要求1不清楚。",
            ]
        ),
        "## 第二阶段：说明书检查\n第二阶段：说明书检查\n- 说明书缺少支持。",
    )

    assert report.count("## 第一阶段：权利要求书检查与特征分解") == 1
    assert report.count("## 第二阶段：说明书检查") == 1
    assert "### 第一阶段审查结果\n- 权利要求1不清楚。" in report
    assert "### 第二阶段审查结果\n- 说明书缺少支持。" in report


def test_failed_worker_task_can_be_retried_after_real_docx_upload(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("UPLOAD_DIR", str(tmp_path))
    monkeypatch.setenv("ENABLE_WORKER_QUEUE", "false")
    monkeypatch.setenv("CODEX_COMMAND", "/bin/false")
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
        settings = type("SettingsStub", (), {"codex_model": "test-model"})()

        def run(self, stage, prompt, on_event, image_paths=None):
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
            prompt="不会写入日志的完整文本",
        )
    except RuntimeError:
        pass

    log = db_session.scalar(select(ModelCallLog).where(ModelCallLog.task_id == task.id))
    assert log is not None
    assert log.status == "failed"
    assert log.stage == "stage_two"
    assert "RuntimeError" in (log.error_message or "")
    assert "不会写入日志的完整文本" not in (log.error_message or "")


def test_call_and_log_persists_codex_events(db_session: Session) -> None:
    class EventClient:
        settings = type("SettingsStub", (), {"codex_model": "codex-test-model"})()

        def run(self, stage, prompt, on_event, image_paths=None):
            on_event(
                CodexEvent(
                    stage=stage,
                    event_type="thread.started",
                    message="Codex 会话已启动。",
                    raw_payload={"type": "thread.started", "thread_id": "thread-1"},
                )
            )
            return CodexRunResult(content="阶段输出", thread_id="thread-1", latency_ms=12)

    alice = db_session.scalar(select(User).where(User.username == "alice"))
    assert alice is not None
    task = PatentCheckTask(user_id=alice.id, title="Codex 事件审计任务")
    db_session.add(task)
    db_session.commit()

    result = call_and_log(
        db=db_session,
        task=task,
        client=EventClient(),
        stage="stage_one",
        prompt="请执行第一阶段。",
    )

    event = db_session.scalar(select(PatentCheckEvent).where(PatentCheckEvent.task_id == task.id))
    log = db_session.scalar(select(ModelCallLog).where(ModelCallLog.task_id == task.id))
    assert result.content == "阶段输出"
    assert event is not None
    assert event.message == "Codex 会话已启动。"
    assert event.raw_payload == '{"type": "thread.started", "thread_id": "thread-1"}'
    assert log is not None
    assert log.model == "codex-test-model"
    assert log.status == "succeeded"


def test_call_and_log_passes_visual_attachments_to_codex(
    tmp_path, db_session: Session
) -> None:
    class ImageClient:
        settings = type("SettingsStub", (), {"codex_model": "codex-test-model"})()

        def __init__(self) -> None:
            self.image_paths = None

        def run(self, stage, prompt, on_event, image_paths=None):
            self.image_paths = image_paths
            return CodexRunResult(content="阶段输出", thread_id="thread-1", latency_ms=12)

    image = tmp_path / "figure-1.png"
    image.write_bytes(b"fake-png")
    client = ImageClient()
    alice = db_session.scalar(select(User).where(User.username == "alice"))
    assert alice is not None
    task = PatentCheckTask(user_id=alice.id, title="Codex 图片审计任务")
    db_session.add(task)
    db_session.commit()

    result = call_and_log(
        db=db_session,
        task=task,
        client=client,
        stage="stage_two",
        prompt="请执行第二阶段。",
        image_paths=[image],
    )

    assert result.content == "阶段输出"
    assert client.image_paths == [image]
