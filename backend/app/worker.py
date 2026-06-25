"""这个文件用于执行 Redis/RQ 中的专利审查异步任务。"""

import json
import logging
import re
from datetime import UTC, datetime
from pathlib import Path

from rq.timeouts import JobTimeoutException
from sqlalchemy.orm import selectinload

from app.core.config import get_settings
from app.core.logging import configure_logging
from app.db.session import SessionLocal
from app.models.model_call_log import ModelCallLog
from app.models.patent_check_task import PROGRESS_STAGE_DEFAULTS, PatentCheckTask
from app.services.errors import UserFacingError
from app.services.model_client import ModelCallResult, ModelClient
from app.services.prompt_loader import load_check_patent_prompt

logger = logging.getLogger(__name__)

STAGE_ONE_OUTPUT_INSTRUCTION = """
输出要求：
- 只输出第一阶段内容，不要输出说明书检查、附图检查或摘要检查。
- 问题项按严重程度排序，优先列出最关键的 8 项以内。
- 《技术特征分解与需说明书解释项清单》应聚焦第二阶段必须核对的关键技术特征，原则上不超过 20 行。
- 每个问题的建议修改保持可执行，但避免展开模板中的全部检查清单。
""".strip()

STAGE_TWO_OUTPUT_INSTRUCTION = """
输出要求：
- 只输出第二阶段、附图与摘要检查、总体评价。
- 必须包含“权要特征-说明书解释对应检查表”。
- 问题项按严重程度排序，优先列出最关键的 10 项以内。
- 不要重复第一阶段完整报告，只引用需说明书解释项清单中的必要特征。
""".strip()


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

        logger.info("patent_task_started task_id=%s user_id=%s", task.id, task.user_id)
        task.status = "running"
        task.started_at = datetime.now(UTC)
        task.error_message = None
        set_task_progress(task, "preparing", "正在准备审查材料。")
        db.commit()

        try:
            payload = load_process_text(task)
            prompt = load_check_patent_prompt()
            client = ModelClient(settings)

            set_task_progress(task, "stage_one", "正在执行第一阶段：权利要求书检查与特征分解。")
            db.commit()
            stage_one = call_and_log(
                db=db,
                task=task,
                client=client,
                stage="stage_one",
                messages=build_stage_one_messages(prompt, payload, task.technical_field),
            )
            task.stage_one_result = stage_one.content
            set_task_progress(
                task,
                "stage_two",
                "第一阶段完成，正在执行第二阶段：说明书、附图与摘要检查。",
            )
            db.commit()
            logger.info(
                "patent_task_stage_completed task_id=%s stage=stage_one output_chars=%s",
                task.id,
                len(stage_one.content),
            )

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

    stage_prompt = build_stage_prompt(prompt, "stage_one")
    return [
        {"role": "system", "content": stage_prompt},
        {
            "role": "user",
            "content": "\n".join(
                [
                    "请仅执行第一阶段：权利要求书检查与特征分解。",
                    f"技术领域：{technical_field or '未填写'}",
                    "请输出通过项、问题项，以及《技术特征分解与需说明书解释项清单》。",
                    STAGE_ONE_OUTPUT_INSTRUCTION,
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

    stage_prompt = build_stage_prompt(prompt, "stage_two")
    stage_one_bridge = extract_stage_one_bridge(stage_one_result)
    return [
        {"role": "system", "content": stage_prompt},
        {
            "role": "user",
            "content": "\n".join(
                [
                    "请执行第二阶段：说明书、附图说明和摘要检查。",
                    f"技术领域：{technical_field or '未填写'}",
                    "必须基于第一阶段的需说明书解释项清单逐项检查说明书支持情况。",
                    "【第一阶段结果】",
                    stage_one_bridge,
                    STAGE_TWO_OUTPUT_INSTRUCTION,
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


def build_stage_prompt(prompt: str, stage: str) -> str:
    """Build a compact prompt containing only rules relevant to one review stage."""

    common = "\n\n".join(
        part
        for part in [
            extract_intro(prompt),
            extract_named_section(prompt, "## 五、输出格式", "## 严重程度定义"),
            extract_named_section(prompt, "## 严重程度定义", "## 工作指令"),
        ]
        if part
    )
    if stage == "stage_one":
        stage_rules = extract_named_section(prompt, "## 第一阶段", "## 第二阶段")
        return "\n\n".join(
            [
                common,
                stage_rules,
                STAGE_ONE_OUTPUT_INSTRUCTION,
            ]
        ).strip()
    if stage == "stage_two":
        stage_rules = "\n\n".join(
            part
            for part in [
                extract_named_section(prompt, "## 第二阶段", "## 三、说明书附图检查清单"),
                extract_named_section(
                    prompt,
                    "## 三、说明书附图检查清单",
                    "## 四、说明书摘要检查清单",
                ),
                extract_named_section(prompt, "## 四、说明书摘要检查清单", "## 五、输出格式"),
            ]
            if part
        )
        return "\n\n".join(
            [
                common,
                stage_rules,
                STAGE_TWO_OUTPUT_INSTRUCTION,
            ]
        ).strip()
    raise ValueError(f"Unknown stage: {stage}")


def extract_intro(prompt: str) -> str:
    """Extract the shared role and goal from the full patent-check prompt."""

    return prompt.split("## 第一阶段", 1)[0].strip()


def extract_named_section(prompt: str, start_marker: str, end_marker: str) -> str:
    """Extract one Markdown section by start and end markers."""

    start = prompt.find(start_marker)
    if start == -1:
        return ""
    end = prompt.find(end_marker, start + len(start_marker))
    if end == -1:
        return prompt[start:].strip()
    return prompt[start:end].strip()


def extract_stage_one_bridge(stage_one_result: str, max_chars: int = 12_000) -> str:
    """Extract the feature-explanation checklist needed by the second stage."""

    lines = stage_one_result.splitlines()
    start_index = next(
        (
            index
            for index, line in enumerate(lines)
            if "技术特征分解与需说明书解释项清单" in line
        ),
        None,
    )
    if start_index is None:
        return truncate_text(stage_one_result, max_chars)

    selected: list[str] = []
    for line in lines[start_index:]:
        if selected and re.match(r"^##\s+", line):
            break
        selected.append(line)
    return truncate_text("\n".join(selected).strip(), max_chars)


def truncate_text(text: str, max_chars: int) -> str:
    """Limit text passed between model stages while preserving a clear marker."""

    if len(text) <= max_chars:
        return text
    return text[:max_chars].rstrip() + "\n\n[内容过长，已截断]"


def set_task_progress(task: PatentCheckTask, stage: str, message: str) -> None:
    """Update task progress fields with the default percentage for the stage."""

    task.progress_stage = stage
    task.progress_percent = PROGRESS_STAGE_DEFAULTS[stage]
    task.progress_message = message


def call_and_log(
    db,
    task: PatentCheckTask,
    client: ModelClient,
    stage: str,
    messages: list[dict[str, str]],
) -> ModelCallResult:
    """Call the model and persist an audit log row."""

    logger.info("model_stage_started task_id=%s stage=%s", task.id, stage)
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
        logger.info(
            "model_stage_succeeded task_id=%s stage=%s latency_ms=%s output_tokens=%s",
            task.id,
            stage,
            result.latency_ms,
            result.output_tokens,
        )
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
        logger.warning(
            "model_stage_failed task_id=%s stage=%s error_type=%s message=%s",
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
                model=client.settings.gpt_model,
                stage=stage,
                status="failed",
                error_message=message[:2000],
            )
        )
        db.commit()
        logger.exception(
            "model_stage_unexpected_failed task_id=%s stage=%s error_type=%s",
            task.id,
            stage,
            type(exc).__name__,
        )
        raise


def normalize_final_report(stage_one: str, stage_two: str) -> str:
    """Combine model outputs into the PRD-required final Markdown report."""

    normalized_stage_one = strip_report_title(stage_one)
    normalized_stage_two = strip_report_title(stage_two)
    return "\n\n".join(
        [
            "# 专利文件检查报告",
            "## 第一阶段：权利要求书检查与特征分解",
            normalized_stage_one,
            "## 第二阶段：说明书检查",
            normalized_stage_two,
        ]
    )


def strip_report_title(markdown: str) -> str:
    """Remove duplicate top-level report titles from model stage output."""

    lines = markdown.strip().splitlines()
    while lines and not lines[0].strip():
        lines.pop(0)
    if lines and lines[0].strip() == "# 专利文件检查报告":
        lines.pop(0)
        while lines and not lines[0].strip():
            lines.pop(0)
    return "\n".join(lines).strip()


def cleanup_task_inputs(db, task: PatentCheckTask) -> None:
    """Delete raw uploads and keep retry input only when a failed task can retry."""

    for file in task.files:
        if file.stored_path:
            Path(file.stored_path).unlink(missing_ok=True)
            file.stored_path = None

    process_text_path = Path(task.process_text_path) if task.process_text_path else None
    if task.status == "failed" and process_text_path and process_text_path.exists():
        task.input_cleanup_status = "retryable"
    else:
        if process_text_path:
            process_text_path.unlink(missing_ok=True)
            task.process_text_path = None
        task.input_cleanup_status = "cleaned"
    db.commit()
