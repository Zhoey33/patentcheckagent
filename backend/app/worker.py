"""这个文件用于执行 Redis/RQ 中的专利审查异步任务。"""

import json
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy.orm import selectinload

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.models.model_call_log import ModelCallLog
from app.models.patent_check_task import PatentCheckTask
from app.services.errors import UserFacingError
from app.services.model_client import ModelCallResult, ModelClient
from app.services.prompt_loader import load_check_patent_prompt


def run_patent_check_task(task_id: str) -> None:
    """Run the two-stage patent check task and persist the final report."""

    settings = get_settings()
    with SessionLocal() as db:
        task = (
            db.query(PatentCheckTask)
            .options(selectinload(PatentCheckTask.files))
            .filter(PatentCheckTask.id == task_id)
            .one_or_none()
        )
        if task is None:
            return

        task.status = "running"
        task.started_at = datetime.now(UTC)
        task.error_message = None
        db.commit()

        try:
            payload = load_process_text(task)
            prompt = load_check_patent_prompt()
            client = ModelClient(settings)

            stage_one = call_and_log(
                db=db,
                task=task,
                client=client,
                stage="stage_one",
                messages=build_stage_one_messages(prompt, payload, task.technical_field),
            )
            task.stage_one_result = stage_one.content
            db.commit()

            stage_two = call_and_log(
                db=db,
                task=task,
                client=client,
                stage="stage_two",
                messages=build_stage_two_messages(
                    prompt,
                    payload,
                    task.technical_field,
                    stage_one.content,
                ),
            )

            task.final_report = normalize_final_report(stage_one.content, stage_two.content)
            task.status = "succeeded"
            task.finished_at = datetime.now(UTC)
            db.commit()
        except UserFacingError as exc:
            task.status = "failed"
            task.error_message = exc.message
            task.finished_at = datetime.now(UTC)
            db.commit()
        except Exception:
            task.status = "failed"
            task.error_message = "任务执行异常，请联系系统管理员。"
            task.finished_at = datetime.now(UTC)
            db.commit()
        finally:
            cleanup_task_inputs(db, task)


def load_process_text(task: PatentCheckTask) -> dict[str, str]:
    """Load extracted texts persisted when the task was created."""

    if not task.process_text_path:
        raise UserFacingError("任务过程文本已清理，无法重试，请重新提交文件。")
    path = Path(task.process_text_path)
    if not path.exists():
        raise UserFacingError("任务过程文本不存在，无法执行审查，请重新提交文件。")
    return json.loads(path.read_text(encoding="utf-8"))


def build_stage_one_messages(
    prompt: str, payload: dict[str, str], technical_field: str | None
) -> list[dict[str, str]]:
    """Build model messages for claims checking and feature decomposition."""

    return [
        {"role": "system", "content": prompt},
        {
            "role": "user",
            "content": "\n".join(
                [
                    "请仅执行第一阶段：权利要求书检查与特征分解。",
                    f"技术领域：{technical_field or '未填写'}",
                    "请输出通过项、问题项，以及《技术特征分解与需说明书解释项清单》。",
                    "【权利要求书】",
                    payload.get("claims", ""),
                ]
            ),
        },
    ]


def build_stage_two_messages(
    prompt: str,
    payload: dict[str, str],
    technical_field: str | None,
    stage_one_result: str,
) -> list[dict[str, str]]:
    """Build model messages for specification, drawings and abstract checking."""

    return [
        {"role": "system", "content": prompt},
        {
            "role": "user",
            "content": "\n".join(
                [
                    "请执行第二阶段：说明书、附图说明和摘要检查。",
                    f"技术领域：{technical_field or '未填写'}",
                    "必须基于第一阶段的需说明书解释项清单逐项检查说明书支持情况。",
                    "【第一阶段结果】",
                    stage_one_result,
                    "【说明书】",
                    payload.get("specification", ""),
                    "【附图说明】",
                    payload.get("drawings", ""),
                    "【摘要】",
                    payload.get("abstract", "未提供摘要文件。"),
                ]
            ),
        },
    ]


def call_and_log(
    db,
    task: PatentCheckTask,
    client: ModelClient,
    stage: str,
    messages: list[dict[str, str]],
) -> ModelCallResult:
    """Call the model and persist an audit log row."""

    try:
        result = client.chat(messages)
        db.add(
            ModelCallLog(
                task_id=task.id,
                model=client.settings.gpt_model,
                stage=stage,
                input_tokens=result.input_tokens,
                output_tokens=result.output_tokens,
                latency_ms=result.latency_ms,
                status="succeeded",
            )
        )
        db.commit()
        return result
    except UserFacingError as exc:
        db.add(
            ModelCallLog(
                task_id=task.id,
                model=client.settings.gpt_model,
                stage=stage,
                status="failed",
                error_message=exc.message,
            )
        )
        db.commit()
        raise


def normalize_final_report(stage_one: str, stage_two: str) -> str:
    """Combine model outputs into the PRD-required final Markdown report."""

    if "# 专利文件检查报告" in stage_two:
        return stage_two
    return "\n\n".join(
        [
            "# 专利文件检查报告",
            "## 第一阶段：权利要求书检查与特征分解",
            stage_one.strip(),
            "## 第二阶段：说明书检查",
            stage_two.strip(),
        ]
    )


def cleanup_task_inputs(db, task: PatentCheckTask) -> None:
    """Delete uploaded files and process text after task completion or failure."""

    for file in task.files:
        if file.stored_path:
            Path(file.stored_path).unlink(missing_ok=True)
            file.stored_path = None

    if task.process_text_path:
        Path(task.process_text_path).unlink(missing_ok=True)
        task.process_text_path = None

    task.input_cleanup_status = "cleaned"
    db.commit()
