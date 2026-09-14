"""Skill 管理权限、任务快照和原文件执行链路。"""

from pathlib import Path

import pytest
from sqlalchemy import select

from app.models.patent_check_task import PatentCheckTask
from app.models.review_skill import ReviewSkill
from app.services.codex_client import CodexRunResult
from app.services.skill_service import validate_skill_files


def login(client, username="admin"):
    assert (
        client.post(
            "/api/auth/login", json={"username": username, "password": "password123"}
        ).status_code
        == 200
    )


def bundle(name="custom-review", instruction="检查原文依据"):
    return {
        "SKILL.md": f"---\nname: {name}\ndescription: 审查专利文件\n---\n\n{instruction}\n",
        "references/claims.md": "# 权利要求规则\n核查引用基础。\n",
    }


def test_skill_management_permissions_validation_and_default(client):
    assert client.get("/api/skills").status_code == 401
    login(client, "alice")
    defaults = client.get("/api/skills").json()["items"]
    assert len(defaults) == 1 and defaults[0]["is_default"]
    assert "files" not in defaults[0]
    assert client.get("/api/admin/skills").status_code == 403
    assert (
        client.post(
            "/api/admin/skills", json={"display_name": "test", "files": bundle()}
        ).status_code
        == 403
    )
    login(client)
    created = client.post(
        "/api/admin/skills", json={"display_name": "自定义审查", "files": bundle()}
    )
    assert created.status_code == 200
    skill = created.json()
    assert skill["version"] == 1 and skill["files"] == bundle()
    assert (
        client.post(
            "/api/admin/skills", json={"display_name": "重名", "files": bundle()}
        ).status_code
        == 409
    )
    disabled = {**skill, "is_enabled": False}
    assert client.put(f"/api/admin/skills/{skill['id']}", json=disabled).status_code == 200
    assert client.post(f"/api/admin/skills/{skill['id']}/default").status_code == 400
    assert len(client.get("/api/skills").json()["items"]) == 1
    assert client.put(f"/api/admin/skills/{skill['id']}", json=skill).status_code == 409
    skill["version"] = 2
    saved = client.put(f"/api/admin/skills/{skill['id']}", json=skill).json()
    assert saved["version"] == 3
    assert client.post(f"/api/admin/skills/{skill['id']}/default").status_code == 200
    items = client.get("/api/admin/skills").json()["items"]
    assert [item["id"] for item in items if item["is_default"]] == [skill["id"]]
    assert client.delete(f"/api/admin/skills/{skill['id']}").status_code == 400
    assert (
        client.put(
            f"/api/admin/skills/{skill['id']}", json={**saved, "is_enabled": False}
        ).status_code
        == 400
    )
    assert client.post(f"/api/admin/skills/{defaults[0]['id']}/default").status_code == 200
    assert client.delete(f"/api/admin/skills/{skill['id']}").status_code == 204


@pytest.mark.parametrize(
    "files",
    [
        {},
        {"SKILL.md": "# No metadata"},
        {"SKILL.md": "---\nname: [wrong]\n---\nbody"},
        {**bundle(), "../outside.md": "bad"},
        {**bundle(), "references/../../outside.md": "bad"},
        {**bundle(), "scripts/run.py": "bad"},
        {**bundle(), "references//extra.md": "bad"},
    ],
)
def test_invalid_skill_bundles_are_rejected(files):
    from app.services.errors import UserFacingError

    with pytest.raises(UserFacingError):
        validate_skill_files(files)


def test_task_keeps_originals_and_skill_snapshot_across_edits_and_deletion(client, db_session):
    login(client)
    client.get("/api/skills")
    old_files = bundle()
    skill = client.post(
        "/api/admin/skills", json={"display_name": "自定义审查", "files": old_files}
    ).json()
    raw = b"%PDF-1.4\x00\xff original document"
    response = client.post(
        "/api/patent-checks",
        data={"title": "快照测试", "skill_id": skill["id"]},
        files={
            role: (f"{role}.pdf", raw, "application/pdf") for role in ("claims", "specification")
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["skill_name"] == "自定义审查" and payload["skill_version"] == 1
    assert "skill_snapshot" not in payload
    task = db_session.get(PatentCheckTask, payload["id"])
    assert task.process_text_path is None
    for file in task.files:
        assert Path(file.stored_path).read_bytes() == raw
        assert file.extraction_status == "original" and file.extracted_text_length == 0
    assert (
        client.put(
            f"/api/admin/skills/{skill['id']}",
            json={**skill, "files": bundle(instruction="新版规则")},
        ).status_code
        == 200
    )
    assert client.delete(f"/api/admin/skills/{skill['id']}").status_code == 204
    db_session.refresh(task)
    assert task.skill_snapshot["files"] == old_files
    assert task.skill_snapshot["version"] == 1
    task.status = "failed"
    db_session.commit()
    assert client.post(f"/api/patent-checks/{task.id}/retry").status_code == 200


def test_worker_runs_original_files_with_skill_and_full_stage_bridge(
    client, db_session, monkeypatch
):
    login(client)
    raw = b"%PDF-1.4 original"
    response = client.post(
        "/api/patent-checks",
        files={
            role: (f"{role}.pdf", raw, "application/pdf") for role in ("claims", "specification")
        },
    )
    task_id = response.json()["id"]
    first_report = "# 第一阶段：权利要求书检查与特征分解\n" + "\n".join(
        f"| C1-F{i} | 特征 {i} |" for i in range(45)
    )
    calls = []

    class FileClient:
        def __init__(self, settings, workspace, isolated):
            self.settings, self.workspace = settings, workspace
            assert isolated
            assert settings.codex_skill_path.name == "SKILL.md"
            assert (settings.codex_skill_path.parent / "references/claims.md").is_file()

        def run(self, stage, prompt, on_event, image_paths):
            assert (self.workspace / "inputs/claims.pdf").read_bytes() == raw
            assert (self.workspace / "inputs/specification.pdf").read_bytes() == raw
            assert "%PDF" not in prompt
            calls.append(stage)
            if stage == "stage_two":
                assert (self.workspace / "stage-one.md").read_text() == first_report
            return CodexRunResult(
                first_report if stage == "stage_one" else "# 第二阶段：说明书检查\n核查结果",
                "test",
                10,
            )

    monkeypatch.setattr("app.worker.SessionLocal", lambda: db_session)
    monkeypatch.setattr("app.worker.CodexClient", FileClient)
    from app.worker import run_patent_check_task

    run_patent_check_task(task_id)
    task = db_session.get(PatentCheckTask, task_id)
    assert task.status == "succeeded" and task.input_cleanup_status == "cleaned"
    assert calls == ["stage_one", "stage_two"] and "C1-F44" in task.final_report
    assert all(file.stored_path is None for file in task.files)
    assert db_session.scalar(select(ReviewSkill.id))


def test_file_tool_outputs_are_not_retained_as_process_text(db_session):
    import json

    from app.models.patent_check_event import PatentCheckEvent
    from app.models.user import User
    from app.services.codex_client import CodexEvent
    from app.worker import persist_codex_event

    user = db_session.scalar(select(User).where(User.username == "alice"))
    task = PatentCheckTask(user_id=user.id)
    db_session.add(task)
    db_session.commit()
    persist_codex_event(
        db_session,
        task,
        CodexEvent(
            stage="stage_one",
            event_type="item.completed",
            message="读取完成",
            raw_payload={
                "type": "item.completed",
                "item": {
                    "type": "command_execution",
                    "status": "completed",
                    "exit_code": 0,
                    "command": "read input",
                    "aggregated_output": "private document content",
                },
            },
        ),
    )
    saved = db_session.scalar(select(PatentCheckEvent).where(PatentCheckEvent.task_id == task.id))
    assert "private document content" not in saved.raw_payload
    assert json.loads(saved.raw_payload)["item"]["exit_code"] == 0
