"""这个文件用于执行 Redis/RQ 中的专利审查异步任务。"""

import json
import logging
import shutil
from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory

from rq.timeouts import JobTimeoutException
from sqlalchemy.orm import selectinload

from app.core.config import get_settings
from app.core.logging import configure_logging
from app.db.session import SessionLocal
from app.models.model_call_log import ModelCallLog
from app.models.patent_check_event import PatentCheckEvent
from app.models.patent_check_task import PROGRESS_STAGE_DEFAULTS, PatentCheckTask
from app.services.codex_client import CodexClient, CodexEvent, CodexRunResult
from app.services.errors import UserFacingError
from app.services.skill_service import materialize_skill, snapshot_skill

logger = logging.getLogger(__name__)


class TaskCancelledError(Exception):
    """Raised when a user cancels a task while the worker is running."""


def run_patent_check_task(task_id: str) -> None:
    """Run the two-stage patent check task and persist the final report."""

    settings = get_settings()
    configure_logging(settings)
    with SessionLocal() as db:
        task = (
            db.query(PatentCheckTask)
            .options(selectinload(PatentCheckTask.files))
            .filter(PatentCheckTask.id == task_id)
            .one_or_none()
        )
        if task is None:
            return
        if task.status == "cancelled":
            return

        logger.info("patent_task_started task_id=%s user_id=%s", task.id, task.user_id)
        task.status = "running"
        task.started_at = datetime.now(UTC)
        task.error_message = None
        set_task_progress(task, "preparing", "正在准备审查材料。")
        db.commit()

        try:
            ensure_task_not_cancelled(db, task)
            settings.upload_dir.mkdir(parents=True, exist_ok=True)
            with TemporaryDirectory(
                prefix=f"task-work-{task.id}-", dir=settings.upload_dir
            ) as work:
                workspace = Path(work).resolve()
                skill = task.skill_snapshot or snapshot_skill(db, None)
                skill_path = materialize_skill(skill, workspace)
                file_paths = prepare_original_files(task, workspace)
                client_settings = settings.model_copy(update={"codex_skill_path": skill_path})
                client = CodexClient(client_settings, workspace=workspace, isolated=True)

                set_task_progress(task, "stage_one", "正在读取权利要求原文件并执行所选 Skill。")
                db.commit()
                stage_one = call_and_log(
                    db,
                    task,
                    client,
                    "stage_one",
                    build_file_review_prompt("stage_one", file_paths, task.technical_field),
                )
                ensure_task_not_cancelled(db, task)
                task.stage_one_result = stage_one.content
                (workspace / "stage-one.md").write_text(stage_one.content, encoding="utf-8")
                set_task_progress(task, "stage_two", "正在按 Skill 核对说明书、附图和摘要原文件。")
                db.commit()
                stage_two = call_and_log(
                    db,
                    task,
                    client,
                    "stage_two",
                    build_file_review_prompt("stage_two", file_paths, task.technical_field),
                )

            ensure_task_not_cancelled(db, task)
            set_task_progress(task, "finalizing", "第二阶段完成，正在整理最终 Markdown 报告。")
            task.final_report = normalize_final_report(stage_one.content, stage_two.content)
            task.status = "succeeded"
            set_task_progress(task, "completed", "审查完成，报告已生成。")
            task.finished_at = datetime.now(UTC)
            db.commit()
            logger.info(
                "patent_task_succeeded task_id=%s final_report_chars=%s",
                task.id,
                len(task.final_report or ""),
            )
        except TaskCancelledError:
            logger.info("patent_task_cancelled task_id=%s", task.id)
            task.status = "cancelled"
            task.progress_message = "用户已取消审查。"
            task.error_message = None
            task.finished_at = task.finished_at or datetime.now(UTC)
            db.commit()
        except UserFacingError as exc:
            logger.warning(
                "patent_task_failed task_id=%s error_type=%s message=%s",
                task.id,
                type(exc).__name__,
                exc.message,
            )
            task.status = "failed"
            task.progress_message = exc.message
            task.error_message = exc.message
            task.finished_at = datetime.now(UTC)
            db.commit()
        except JobTimeoutException:
            logger.exception("patent_task_timeout task_id=%s", task.id)
            task.status = "failed"
            task.error_message = "任务执行超时，请联系系统管理员或稍后重试。"
            task.progress_message = task.error_message
            task.finished_at = datetime.now(UTC)
            db.commit()
        except Exception as exc:
            logger.exception(
                "patent_task_unexpected_failed task_id=%s error_type=%s",
                task.id,
                type(exc).__name__,
            )
            task.status = "failed"
            task.error_message = f"任务执行异常（{type(exc).__name__}），请联系系统管理员。"
            task.progress_message = task.error_message
            task.finished_at = datetime.now(UTC)
            db.commit()
        finally:
            cleanup_task_inputs(db, task)


def prepare_original_files(task: PatentCheckTask, workspace: Path) -> dict[str, str]:
    """Copy only this task's original uploads into its Codex workspace."""
    paths = {}
    inputs = workspace / "inputs"
    inputs.mkdir()
    for file in task.files:
        if not file.stored_path or not Path(file.stored_path).is_file():
            raise UserFacingError("任务原文件已清理或不存在，请重新上传。")
        source = Path(file.stored_path)
        target = inputs / f"{file.file_role}{source.suffix.lower()}"
        shutil.copyfile(source, target)
        target.chmod(0o444)
        paths[file.file_role] = str(target.relative_to(workspace))
    if not {"claims", "specification"} <= paths.keys():
        raise UserFacingError("任务缺少权利要求书或说明书原文件，请重新上传。")
    return paths


def build_file_review_prompt(stage: str, files: dict[str, str], technical_field: str | None) -> str:
    roles = {
        "claims": "权利要求书",
        "specification": "说明书",
        "drawings": "附图",
        "abstract": "摘要",
    }
    lines = [f"技术领域：{technical_field or '未填写'}"]
    if stage == "stage_one":
        lines.append("仅执行 Skill 的第一阶段：权利要求书检查与特征分解。")
        selected = {"claims": files["claims"]}
    else:
        lines.append(
            "执行 Skill 的第二阶段：说明书、附图与摘要检查。"
            "先读取 stage-one.md 中的第一阶段报告，沿用技术特征编号。"
        )
        selected = files
    lines.append("以下为原文件路径，请自行调用文件工具读取；上传阶段没有提取文字或转换页面：")
    lines.extend(f"- {roles[role]}：{path}" for role, path in selected.items())
    lines.append(
        "按 Skill 输出本阶段 Markdown 报告，首行使用对应阶段的 # 标题。正文不包含执行计划。"
    )
    return "\n".join(lines)


def set_task_progress(task: PatentCheckTask, stage: str, message: str) -> None:
    """Update task progress fields with the default percentage for the stage."""

    task.progress_stage = stage
    task.progress_percent = PROGRESS_STAGE_DEFAULTS[stage]
    task.progress_message = message


def ensure_task_not_cancelled(db, task: PatentCheckTask) -> None:
    """Stop the worker at safe boundaries after a user cancellation."""

    db.refresh(task)
    if task.status == "cancelled":
        raise TaskCancelledError


def call_and_log(
    db,
    task: PatentCheckTask,
    client: CodexClient,
    stage: str,
    prompt: str,
    image_paths: list[Path] | None = None,
) -> CodexRunResult:
    """Run Codex and persist audit log plus user-visible execution events."""

    logger.info("codex_stage_started task_id=%s stage=%s", task.id, stage)
    try:
        result = client.run(
            stage=stage,
            prompt=prompt,
            on_event=lambda event: persist_codex_event(db, task, event),
            image_paths=image_paths,
        )
        db.add(
            ModelCallLog(
                task_id=task.id,
                model=get_codex_model_name(client),
                stage=stage,
                input_tokens=None,
                output_tokens=None,
                latency_ms=result.latency_ms,
                status="succeeded",
            )
        )
        db.commit()
        logger.info(
            "codex_stage_succeeded task_id=%s stage=%s latency_ms=%s thread_id=%s",
            task.id,
            stage,
            result.latency_ms,
            result.thread_id,
        )
        return result
    except UserFacingError as exc:
        db.add(
            ModelCallLog(
                task_id=task.id,
                model=get_codex_model_name(client),
                stage=stage,
                status="failed",
                error_message=exc.message,
            )
        )
        db.commit()
        logger.warning(
            "codex_stage_failed task_id=%s stage=%s error_type=%s message=%s",
            task.id,
            stage,
            type(exc).__name__,
            exc.message,
        )
        raise
    except Exception as exc:
        message = f"{type(exc).__name__}: {exc}"
        db.add(
            ModelCallLog(
                task_id=task.id,
                model=get_codex_model_name(client),
                stage=stage,
                status="failed",
                error_message=message[:2000],
            )
        )
        db.commit()
        logger.exception(
            "codex_stage_unexpected_failed task_id=%s stage=%s error_type=%s",
            task.id,
            stage,
            type(exc).__name__,
        )
        raise


def persist_codex_event(db, task: PatentCheckTask, event: CodexEvent) -> None:
    """Persist one Codex execution event and surface it as current task progress."""

    db.refresh(task)
    # File tools can return entire documents; retain status metadata and report snapshots only.
    raw_payload = {
        key: event.raw_payload[key]
        for key in ("type", "thread_id", "usage")
        if key in event.raw_payload
    }
    if event.event_type == "report_snapshot":
        raw_payload["content"] = event.content
    elif isinstance(event.raw_payload.get("item"), dict):
        item = event.raw_payload["item"]
        raw_payload["item"] = {
            key: item[key] for key in ("id", "type", "status", "exit_code") if key in item
        }
    db.add(
        PatentCheckEvent(
            task_id=task.id,
            stage=event.stage,
            event_type=event.event_type,
            message=event.message,
            raw_payload=json.dumps(raw_payload, ensure_ascii=False),
        )
    )
    if event.event_type != "report_snapshot" and task.status != "cancelled":
        task.progress_message = event.message[:255]
    db.commit()


def get_codex_model_name(client: CodexClient) -> str:
    """Return a stable model label for Codex audit rows."""

    return getattr(client.settings, "codex_model", None) or "codex"


def normalize_final_report(stage_one: str, stage_two: str) -> str:
    """Combine model outputs into the PRD-required final Markdown report."""

    normalized_stage_one = normalize_stage_body(
        stage_one,
        stage_heading="第一阶段：权利要求书检查与特征分解",
        fallback_heading="第一阶段审查结果",
    )
    normalized_stage_two = normalize_stage_body(
        stage_two,
        stage_heading="第二阶段：说明书检查",
        fallback_heading="第二阶段审查结果",
    )
    return "\n\n".join(
        [
            "# 专利文件检查报告",
            "## 第一阶段：权利要求书检查与特征分解",
            normalized_stage_one,
            "## 第二阶段：说明书检查",
            normalized_stage_two,
        ]
    )


def normalize_stage_body(markdown: str, stage_heading: str, fallback_heading: str) -> str:
    """Remove duplicate report/stage titles and ensure a useful Markdown subheading."""

    lines = strip_leading_report_headings(markdown, stage_heading)
    body = "\n".join(lines).strip()
    if not body:
        return f"### {fallback_heading}\n暂无阶段输出。"
    if first_content_line(body).startswith("#"):
        return body
    return f"### {fallback_heading}\n{body}"


def strip_leading_report_headings(markdown: str, stage_heading: str) -> list[str]:
    """Remove repeated top-level and current-stage titles from the beginning."""

    lines = markdown.strip().splitlines()
    while lines and not lines[0].strip():
        lines.pop(0)
    while lines and is_duplicate_report_heading(lines[0], stage_heading):
        lines.pop(0)
        while lines and not lines[0].strip():
            lines.pop(0)
    return lines


def is_duplicate_report_heading(line: str, stage_heading: str) -> bool:
    """Return whether a leading line repeats a wrapper report heading."""

    normalized = line.strip().lstrip("#").strip()
    return normalized in {
        "专利文件检查报告",
        stage_heading,
    }


def first_content_line(markdown: str) -> str:
    """Return the first non-empty line from a Markdown block."""

    for line in markdown.splitlines():
        if line.strip():
            return line.strip()
    return ""


def cleanup_task_inputs(db, task: PatentCheckTask) -> None:
    """Keep failed-task original inputs for retry; clean completed/cancelled inputs."""
    available = bool(task.files) and all(
        file.stored_path and Path(file.stored_path).is_file() for file in task.files
    )
    if task.status == "failed" and available:
        task.input_cleanup_status = "retryable"
    else:
        for file in task.files:
            if file.stored_path:
                Path(file.stored_path).unlink(missing_ok=True)
                file.stored_path = None
        task.input_cleanup_status = "cleaned"
    if task.process_text_path:
        Path(task.process_text_path).unlink(missing_ok=True)
        task.process_text_path = None
    db.commit()
