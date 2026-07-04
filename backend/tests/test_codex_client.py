"""这个文件用于验证 Codex CLI 执行器的事件解析和结果提取。"""

from pathlib import Path

import pytest

from app.core.config import Settings
from app.services.codex_client import CodexClient, parse_codex_event
from app.services.errors import UserFacingError


class FakeCodexProcess:
    """Test double that mimics a Codex JSONL subprocess."""

    def __init__(self, stdout_lines: list[str], stderr_lines: list[str] | None = None) -> None:
        self.stdout = iter(stdout_lines)
        self.stderr = iter(stderr_lines or [])
        self.returncode = 0
        self.args: list[str] | None = None
        self.kwargs = {}
        self.stdin_payload = ""

    def communicate(self, input: str | None = None, timeout: int | None = None):
        self.stdin_payload = input or ""
        return ("\n".join(self.stdout), "\n".join(self.stderr))


def test_codex_client_emits_events_and_extracts_final_message(tmp_path: Path) -> None:
    skill = tmp_path / "check-patent.md"
    skill.write_text("# 专利检查 Skill\n\n请进行专利审查。", encoding="utf-8")
    process = FakeCodexProcess(
        [
            '{"type":"thread.started","thread_id":"thread-1"}',
            '{"type":"turn.started"}',
            '{"type":"response_item","payload":{"type":"message","role":"assistant",'
            '"content":[{"type":"output_text","text":"# 阶段报告\\n- 发现问题"}]}}',
            '{"type":"event_msg","payload":{"type":"task_complete",'
            '"last_agent_message":"# 阶段报告\\n- 发现问题"}}',
        ]
    )
    captured_events = []

    def popen_factory(args, **kwargs):
        process.args = args
        return process

    client = CodexClient(
        Settings(
            app_secret_key="test-secret-key-with-at-least-32-bytes",
            codex_skill_path=skill,
            codex_command="codex",
        ),
        popen_factory=popen_factory,
    )

    result = client.run(
        stage="stage_one",
        prompt="请检查权利要求书。",
        on_event=captured_events.append,
    )

    assert result.content == "# 阶段报告\n- 发现问题"
    assert result.thread_id == "thread-1"
    assert [event.event_type for event in captured_events] == [
        "thread.started",
        "turn.started",
        "report_snapshot",
        "event_msg",
    ]
    assert captured_events[2].content == "# 阶段报告\n- 发现问题"
    assert captured_events[0].message == "第一阶段审查已启动。"
    assert "check-patent.md" in process.stdin_payload
    assert "请检查权利要求书。" in process.stdin_payload
    assert process.args is not None
    assert "--json" in process.args
    assert "--ephemeral" in process.args
    assert "--skip-git-repo-check" in process.args


def test_codex_client_configures_openai_compatible_provider_from_gpt_settings(
    tmp_path: Path,
) -> None:
    skill = tmp_path / "check-patent.md"
    skill.write_text("# 专利检查 Skill", encoding="utf-8")
    process = FakeCodexProcess(
        ['{"type":"event_msg","payload":{"type":"task_complete","last_agent_message":"OK"}}']
    )

    def popen_factory(args, **kwargs):
        process.args = args
        process.kwargs = kwargs
        return process

    client = CodexClient(
        Settings(
            app_secret_key="test-secret-key-with-at-least-32-bytes",
            codex_skill_path=skill,
            codex_command="codex",
            gpt_api_key="test-api-key",
            gpt_base_url="https://helloapi.cc",
            gpt_model="gpt-5.5",
        ),
        popen_factory=popen_factory,
    )

    result = client.run(stage="stage_one", prompt="请审查。", on_event=lambda event: None)

    assert result.content == "OK"
    assert process.args is not None
    assert process.args[:4] == ["codex", "--ask-for-approval", "never", "-m"]
    assert "gpt-5.5" in process.args
    assert '-c' in process.args
    assert 'model_provider="patent-check-gpt"' in process.args
    assert 'model_providers.patent-check-gpt.base_url="https://helloapi.cc/v1"' in process.args
    assert 'model_providers.patent-check-gpt.env_key="CODEX_API_KEY"' in process.args
    assert 'model_providers.patent-check-gpt.wire_api="responses"' in process.args
    assert process.kwargs["env"]["CODEX_API_KEY"] == "test-api-key"


def test_codex_client_uses_configured_sandbox_mode(tmp_path: Path) -> None:
    skill = tmp_path / "check-patent.md"
    skill.write_text("# 专利检查 Skill", encoding="utf-8")
    process = FakeCodexProcess(
        ['{"type":"event_msg","payload":{"type":"task_complete","last_agent_message":"OK"}}']
    )

    def popen_factory(args, **kwargs):
        process.args = args
        return process

    client = CodexClient(
        Settings(
            app_secret_key="test-secret-key-with-at-least-32-bytes",
            codex_skill_path=skill,
            codex_command="codex",
            codex_sandbox_mode="danger-full-access",
        ),
        popen_factory=popen_factory,
    )

    client.run(stage="stage_one", prompt="请审查。", on_event=lambda event: None)

    assert process.args is not None
    assert process.args[process.args.index("--sandbox") + 1] == "danger-full-access"


def test_codex_client_extracts_final_message_from_item_completed_agent_message(
    tmp_path: Path,
) -> None:
    skill = tmp_path / "check-patent.md"
    skill.write_text("# 专利检查 Skill", encoding="utf-8")
    process = FakeCodexProcess(
        [
            '{"type":"item.completed","item":{"id":"item_1","type":"agent_message",'
            '"text":"# 阶段报告\\n- 新版 Codex 输出"}}',
            '{"type":"turn.completed","usage":{"input_tokens":10,"output_tokens":5}}',
        ]
    )

    client = CodexClient(
        Settings(
            app_secret_key="test-secret-key-with-at-least-32-bytes",
            codex_skill_path=skill,
            codex_command="codex",
        ),
        popen_factory=lambda *args, **kwargs: process,
    )

    result = client.run(stage="stage_one", prompt="请审查。", on_event=lambda event: None)

    assert result.content == "# 阶段报告\n- 新版 Codex 输出"


def test_codex_client_describes_events_with_user_readable_stage_messages() -> None:
    examples = [
        (
            "stage_one",
            '{"type":"turn.started"}',
            "正在分析权利要求书并提取关键技术特征。",
        ),
        (
            "stage_two",
            '{"type":"turn.started"}',
            "正在核对说明书、附图和摘要的支持情况。",
        ),
        (
            "stage_two",
            '{"type":"turn.completed"}',
            "第二阶段检查完成，正在整理最终报告。",
        ),
    ]

    for stage, line, expected_message in examples:
        event, _, _ = parse_codex_event(stage, line)

        assert event is not None
        assert event.message == expected_message
        assert "Codex 事件" not in event.message
        assert "item.completed" not in event.message


def test_codex_client_treats_agent_messages_as_content_snapshots() -> None:
    event, _, final_message = parse_codex_event(
        "stage_one",
        '{"type":"item.completed","item":{"type":"agent_message","text":"# 第一阶段报告"}}',
    )

    assert event is None
    assert final_message == "# 第一阶段报告"


def test_codex_client_streams_report_snapshots_without_duplicate_ready_events(
    tmp_path: Path,
) -> None:
    skill = tmp_path / "check-patent.md"
    skill.write_text("# 专利检查 Skill", encoding="utf-8")
    process = FakeCodexProcess(
        [
            '{"type":"thread.started","thread_id":"thread-1"}',
            '{"type":"turn.started"}',
            '{"type":"item.completed","item":{"type":"agent_message",'
            '"text":"## 第一阶段：权利要求书检查与特征分解\\n草稿"}}',
            '{"type":"item.completed","item":{"type":"agent_message",'
            '"text":"## 第一阶段：权利要求书检查与特征分解\\n最终报告"}}',
            '{"type":"event_msg","payload":{"type":"task_complete",'
            '"last_agent_message":"## 第一阶段：权利要求书检查与特征分解\\n最终报告"}}',
        ]
    )
    captured_events = []
    client = CodexClient(
        Settings(
            app_secret_key="test-secret-key-with-at-least-32-bytes",
            codex_skill_path=skill,
            codex_command="codex",
        ),
        popen_factory=lambda *args, **kwargs: process,
    )

    result = client.run(stage="stage_one", prompt="请审查。", on_event=captured_events.append)

    assert result.content == "## 第一阶段：权利要求书检查与特征分解\n最终报告"
    visible_messages = [
        event.message for event in captured_events if event.event_type != "report_snapshot"
    ]
    assert "第一阶段报告已生成。" not in visible_messages
    assert visible_messages == [
        "第一阶段审查已启动。",
        "正在分析权利要求书并提取关键技术特征。",
        "第一阶段检查完成，准备核对说明书支持情况。",
    ]
    snapshots = [event for event in captured_events if event.event_type == "report_snapshot"]
    assert [event.content for event in snapshots] == [
        "## 第一阶段：权利要求书检查与特征分解\n草稿",
        "## 第一阶段：权利要求书检查与特征分解\n最终报告",
    ]


def test_codex_client_maps_nonzero_exit_to_user_facing_error(tmp_path: Path) -> None:
    skill = tmp_path / "check-patent.md"
    skill.write_text("# 专利检查 Skill", encoding="utf-8")
    process = FakeCodexProcess([], ["authentication failed"])
    process.returncode = 1

    client = CodexClient(
        Settings(
            app_secret_key="test-secret-key-with-at-least-32-bytes",
            codex_skill_path=skill,
            codex_command="codex",
        ),
        popen_factory=lambda *args, **kwargs: process,
    )

    with pytest.raises(UserFacingError, match="Codex 执行失败"):
        client.run(stage="stage_one", prompt="请审查。", on_event=lambda event: None)
