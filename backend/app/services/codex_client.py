"""这个文件用于通过 Codex CLI 执行专利审查 skill 并解析实时事件。"""

import json
import logging
import os
import select
import signal
import subprocess
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.core.config import Settings
from app.services.errors import UserFacingError

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CodexEvent:
    stage: str
    event_type: str
    message: str
    raw_payload: dict[str, Any]
    content: str | None = None


@dataclass(frozen=True)
class CodexRunResult:
    content: str
    thread_id: str | None
    latency_ms: int


class CodexClient:
    """Run Codex non-interactively and surface JSONL events."""

    def __init__(
        self,
        settings: Settings,
        popen_factory: Callable[..., Any] = subprocess.Popen,
        workspace: Path | None = None,
        isolated: bool = False,
    ) -> None:
        self.settings = settings
        self.popen_factory = popen_factory
        self.workspace = workspace or Path.cwd()
        self.isolated = isolated

    def run(
        self,
        stage: str,
        prompt: str,
        on_event: Callable[[CodexEvent], None],
        image_paths: list[Path] | None = None,
    ) -> CodexRunResult:
        """Execute Codex with the configured skill and stream parsed events."""

        skill_path = self._resolve_skill_path()
        full_prompt = build_codex_prompt(
            skill_path,
            prompt,
            visual_attachment_count=len(image_paths or []),
        )
        command = self._build_command(image_paths or [])
        started_at = time.perf_counter()
        thread_id: str | None = None
        final_message = ""
        last_report_snapshot = ""
        stderr_lines: list[str] = []

        def handle_stdout_line(line: str) -> None:
            nonlocal thread_id, final_message, last_report_snapshot
            event, next_thread_id, next_final = parse_codex_event(stage, line)
            if next_thread_id:
                thread_id = next_thread_id
            if event:
                on_event(event)
            if next_final:
                final_message = next_final
                if next_final != last_report_snapshot:
                    last_report_snapshot = next_final
                    on_event(build_report_snapshot_event(stage, next_final))

        try:
            process = self.popen_factory(
                command,
                cwd=str(self.workspace),
                env=self._build_environment(),
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
                start_new_session=True,
            )
        except OSError as exc:
            raise UserFacingError("Codex 命令不可用，请联系系统管理员检查部署环境。", 500) from exc

        try:
            if getattr(process, "stdin", None) is not None:
                process.stdin.write(full_prompt)
                process.stdin.close()
            elif hasattr(process, "communicate"):
                stdout_text, stderr_text = process.communicate(
                    input=full_prompt,
                    timeout=self.settings.codex_timeout_seconds,
                )
                for line in stdout_text.splitlines():
                    handle_stdout_line(line)
                returncode = getattr(process, "returncode", 0)
                return self._finish_run(
                    returncode, stderr_text, final_message, thread_id, started_at
                )

            stderr_thread = drain_stream(getattr(process, "stderr", None), stderr_lines)
            if getattr(process, "stdout", None) is not None:
                read_stdout_with_timeout(
                    process,
                    timeout_seconds=self.settings.codex_timeout_seconds,
                    started_at=started_at,
                    on_line=handle_stdout_line,
                )

            returncode = process.wait(timeout=1)
            if stderr_thread:
                stderr_thread.join(timeout=1)
        except subprocess.TimeoutExpired as exc:
            stop_process_group(process)
            raise UserFacingError("Codex 执行超时，请稍后重试。", 504) from exc
        except BaseException:
            if getattr(process, "returncode", None) is None:
                stop_process_group(process)
            raise

        stderr_text = "\n".join(stderr_lines)
        return self._finish_run(returncode, stderr_text, final_message, thread_id, started_at)

    def _finish_run(
        self,
        returncode: int,
        stderr_text: str,
        final_message: str,
        thread_id: str | None,
        started_at: float,
    ) -> CodexRunResult:
        latency_ms = int((time.perf_counter() - started_at) * 1000)
        if returncode != 0:
            logger.warning(
                "codex_run_failed returncode=%s stderr=%s",
                returncode,
                truncate_diagnostic(stderr_text),
            )
            raise UserFacingError("Codex 执行失败，请联系系统管理员检查 Codex 配置。", 502)
        if not final_message.strip():
            raise UserFacingError("Codex 未返回审查结果，请稍后重试。", 502)
        return CodexRunResult(
            content=final_message.strip(),
            thread_id=thread_id,
            latency_ms=latency_ms,
        )

    def _resolve_skill_path(self) -> Path:
        skill_path = self.settings.codex_skill_path
        if not skill_path.is_absolute():
            skill_path = self.workspace / skill_path
        if not skill_path.exists():
            raise UserFacingError(f"Codex skill 不存在：{skill_path}", 500)
        return skill_path

    def _build_command(self, image_paths: list[Path] | None = None) -> list[str]:
        command = [
            self.settings.codex_command,
            "--ask-for-approval",
            "never",
        ]
        effective_model = self.settings.codex_model or self.settings.gpt_model
        if effective_model:
            command.extend(["-m", effective_model])
        command.extend(self._build_provider_config_args())
        command.append("exec")
        for image_path in image_paths or []:
            command.extend(["-i", str(image_path)])
        command.extend(
            [
                "--json",
                "--ephemeral",
                "--skip-git-repo-check",
                *([] if self.isolated else ["--sandbox", self.settings.codex_sandbox_mode]),
                "-C",
                str(self.workspace),
                "-",
            ]
        )
        return command

    def _build_provider_config_args(self) -> list[str]:
        if not self.settings.gpt_base_url:
            return []

        provider_name = "patent-check-gpt"
        base_url = normalize_openai_compatible_base_url(self.settings.gpt_base_url)
        return [
            "-c",
            f'model_provider="{provider_name}"',
            "-c",
            f'model_providers.{provider_name}.name="{provider_name}"',
            "-c",
            f'model_providers.{provider_name}.base_url="{base_url}"',
            "-c",
            f'model_providers.{provider_name}.env_key="CODEX_API_KEY"',
            "-c",
            f'model_providers.{provider_name}.wire_api="responses"',
        ]

    def _build_environment(self) -> dict[str, str]:
        env = os.environ.copy()
        if self.isolated:
            env = {
                key: value
                for key, value in env.items()
                if key in {"PATH", "LANG", "LC_ALL", "SSL_CERT_FILE", "SSL_CERT_DIR"}
            }
            codex_home = self.workspace / ".codex"
            codex_home.mkdir(exist_ok=True)
            (codex_home / "config.toml").write_text(
                'default_permissions = "patent-task"\n'
                "[permissions.patent-task.filesystem]\n"
                '":root" = "deny"\n":minimal" = "read"\n'
                f'{json.dumps(str(self.workspace))} = "write"\n'
                "[permissions.patent-task.network]\nenabled = false\n",
                encoding="utf-8",
            )
            env.update(HOME=str(self.workspace), CODEX_HOME=str(codex_home))
        if self.settings.gpt_api_key and not env.get("CODEX_API_KEY"):
            env["CODEX_API_KEY"] = self.settings.gpt_api_key
        return env


def normalize_openai_compatible_base_url(base_url: str) -> str:
    """Return the API root expected by Codex for OpenAI-compatible gateways."""

    normalized = base_url.rstrip("/")
    if not normalized.endswith("/v1"):
        normalized = f"{normalized}/v1"
    return normalized


def build_codex_prompt(
    skill_path: Path,
    task_prompt: str,
    visual_attachment_count: int = 0,
) -> str:
    """Explicitly invoke the materialized skill; supply paths, not compiled rules."""
    name = skill_path.parent.name if skill_path.name == "SKILL.md" else skill_path.stem
    parts = [
        f"${name}",
        f"请调用这个 Skill：{skill_path}。先读取 SKILL.md，再按其中链接读取当前阶段规则。",
        "使用文件工具读取任务给出的原文件；PDF 必要时渲染后查看图像。中间文件写入当前工作目录。",
        "只处理本次材料，不修改原文件。报告明确标注未能读取或核对的范围。",
    ]
    if visual_attachment_count:
        parts.append(f"本次还附加 {visual_attachment_count} 张图片附件。")
    parts.extend(["<task>", task_prompt, "</task>"])
    return "\n\n".join(parts)


def stop_process_group(process: Any) -> None:
    """Reap the CLI and its file-tool children on timeout or cancellation."""
    if isinstance(process, subprocess.Popen):
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.wait()
    else:
        process.kill()


def parse_codex_event(stage: str, line: str) -> tuple[CodexEvent | None, str | None, str | None]:
    """Parse one Codex JSONL stdout line into a display event and optional final content."""

    line = line.strip()
    if not line:
        return None, None, None
    try:
        payload = json.loads(line)
    except json.JSONDecodeError:
        logger.debug("codex_non_json_stdout line=%s", truncate_diagnostic(line))
        return None, None, None

    event_type = str(payload.get("type") or "unknown")
    thread_id = payload.get("thread_id") if event_type == "thread.started" else None
    final_message = extract_final_message(payload)
    if final_message and is_assistant_content_event(payload):
        return None, thread_id, final_message
    message = describe_codex_event(stage, payload)
    event = CodexEvent(
        stage=stage,
        event_type=event_type,
        message=message,
        raw_payload=payload,
    )
    return event, thread_id, final_message


def describe_codex_event(stage: str, payload: dict[str, Any]) -> str:
    """Return a short user-facing description for a Codex JSON event."""

    event_type = payload.get("type")
    inner = payload.get("payload") if isinstance(payload.get("payload"), dict) else {}
    inner_type = inner.get("type")
    item = payload.get("item") if isinstance(payload.get("item"), dict) else {}
    item_type = item.get("type")
    stage_messages = get_stage_event_messages(stage)
    if event_type == "thread.started":
        return stage_messages["started"]
    if event_type == "turn.started":
        return stage_messages["running"]
    if event_type == "turn.completed":
        return stage_messages["completed"]
    if event_type == "error":
        return "模型服务连接不稳定，系统正在自动重试。"
    if item_type == "command_execution":
        if item.get("status") == "in_progress":
            return "正在读取审查规则或原始材料。"
        if item.get("exit_code") not in (None, 0):
            return "本次文件工具执行未完成，Codex 正在调整读取方式。"
        return "已完成一次材料读取或核对。"
    if inner_type == "task_complete":
        return stage_messages["completed"]
    if inner_type:
        return stage_messages["running"]
    return stage_messages["running"]


def get_stage_event_messages(stage: str) -> dict[str, str]:
    """Return user-readable progress messages for a review stage."""

    if stage == "stage_one":
        return {
            "started": "第一阶段审查已启动。",
            "running": "正在分析权利要求书并提取关键技术特征。",
            "completed": "第一阶段检查完成，准备核对说明书支持情况。",
        }
    if stage == "stage_two":
        return {
            "started": "第二阶段审查已启动。",
            "running": "正在核对说明书、附图和摘要的支持情况。",
            "completed": "第二阶段检查完成，正在整理最终报告。",
        }
    return {
        "started": "审查任务已启动。",
        "running": "正在执行审查任务。",
        "completed": "阶段审查已完成。",
    }


def extract_final_message(payload: dict[str, Any]) -> str | None:
    """Extract the latest assistant Markdown content from known Codex event shapes."""

    inner = payload.get("payload") if isinstance(payload.get("payload"), dict) else {}
    item = payload.get("item") if isinstance(payload.get("item"), dict) else {}
    if item.get("type") == "agent_message" and isinstance(item.get("text"), str):
        return item["text"] if looks_like_review_report(item["text"]) else None
    if isinstance(inner.get("last_agent_message"), str):
        return inner["last_agent_message"]
    if inner.get("type") == "message" and inner.get("role") == "assistant":
        parts = []
        for item in inner.get("content") or []:
            if isinstance(item, dict) and isinstance(item.get("text"), str):
                parts.append(item["text"])
        if parts:
            return "\n".join(parts)
    if payload.get("type") == "message" and payload.get("role") == "assistant":
        content = payload.get("content")
        if isinstance(content, str):
            return content
    return None


def looks_like_review_report(text: str) -> bool:
    """Return whether assistant text is actual Markdown report content, not process chatter."""

    stripped = text.lstrip()
    if stripped.startswith("#"):
        return True
    return "###" in stripped and ("问题" in stripped or "检查" in stripped or "审查" in stripped)


def is_assistant_content_event(payload: dict[str, Any]) -> bool:
    """Return whether a Codex event primarily carries assistant report content."""

    inner = payload.get("payload") if isinstance(payload.get("payload"), dict) else {}
    item = payload.get("item") if isinstance(payload.get("item"), dict) else {}
    if item.get("type") == "agent_message":
        return True
    if inner.get("type") == "message" and inner.get("role") == "assistant":
        return True
    if payload.get("type") == "message" and payload.get("role") == "assistant":
        return True
    return False


def read_stdout_with_timeout(
    process: Any,
    timeout_seconds: int,
    started_at: float,
    on_line: Callable[[str], None],
) -> None:
    """Read subprocess stdout without letting an open pipe bypass the total timeout."""

    stdout = process.stdout
    while True:
        elapsed = time.perf_counter() - started_at
        remaining = timeout_seconds - elapsed
        if remaining <= 0:
            raise subprocess.TimeoutExpired(getattr(process, "args", "codex"), timeout_seconds)

        ready, _, _ = select.select([stdout], [], [], min(1.0, remaining))
        if ready:
            line = stdout.readline()
            if line:
                on_line(line)
                continue

        if process.poll() is not None:
            for line in stdout:
                on_line(line)
            return


def build_report_snapshot_event(stage: str, content: str) -> CodexEvent:
    """Build a non-timeline event carrying the latest stage Markdown snapshot."""

    stage_name = {
        "stage_one": "第一阶段",
        "stage_two": "第二阶段",
    }.get(stage, "阶段")
    return CodexEvent(
        stage=stage,
        event_type="report_snapshot",
        message=f"{stage_name}报告内容已更新。",
        raw_payload={"type": "report_snapshot", "content": content},
        content=content,
    )


def truncate_diagnostic(text: str, max_chars: int = 800) -> str:
    """Limit Codex diagnostic text before writing it to application logs."""

    compact = " ".join(text.split())
    if len(compact) <= max_chars:
        return compact
    return compact[:max_chars].rstrip() + "..."


def drain_stream(stream: Any, lines: list[str]) -> threading.Thread | None:
    """Read a subprocess stream in the background so its pipe cannot block Codex."""

    if stream is None:
        return None

    def read_lines() -> None:
        for line in stream:
            lines.append(str(line).rstrip())

    thread = threading.Thread(target=read_lines, daemon=True)
    thread.start()
    return thread
