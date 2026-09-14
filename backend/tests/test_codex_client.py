"""这个文件用于验证 Codex CLI 执行器的事件解析和结果提取。"""

import stat
import time
from pathlib import Path

import pytest

from app.core.config import Settings
from app.services.codex_client import CodexClient, build_codex_prompt, parse_codex_event
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


def test_build_codex_prompt_invokes_skill_by_name_and_path(tmp_path: Path) -> None:
    skill = tmp_path / "check-patent.md"
    skill.write_text("完整 skill 内容，不应被重复发送。", encoding="utf-8")

    prompt = build_codex_prompt(skill, "【system】\n只执行第一阶段。")

    assert "完整 skill 内容" not in prompt
    assert str(skill) in prompt
    assert "$check-patent" in prompt
    assert "使用文件工具读取" in prompt
    assert "只执行第一阶段" in prompt


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
    assert 'model_reasoning_effort="low"' in process.args
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


def test_codex_client_passes_images_to_codex_exec(tmp_path: Path) -> None:
    skill = tmp_path / "check-patent.md"
    image = tmp_path / "figure-1.png"
    skill.write_text("# 专利检查 Skill", encoding="utf-8")
    image.write_bytes(b"fake-png")
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
        ),
        popen_factory=popen_factory,
    )

    client.run(
        stage="stage_two",
        prompt="请审查附图。",
        on_event=lambda event: None,
        image_paths=[image],
    )

    assert process.args is not None
    exec_index = process.args.index("exec")
    assert process.args[exec_index + 1 : exec_index + 3] == ["-i", str(image)]
    assert "附加 1 张图片附件" in process.stdin_payload
    assert "纯文本专利审查" not in process.stdin_payload


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
    assert result.usage == {"input_tokens": 10, "output_tokens": 5}


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


def test_codex_client_ignores_agent_process_chatter_until_report(tmp_path: Path) -> None:
    skill = tmp_path / "check-patent.md"
    skill.write_text("# 专利检查 Skill", encoding="utf-8")
    process = FakeCodexProcess(
        [
            '{"type":"item.completed","item":{"id":"item_1","type":"agent_message",'
            '"text":"我会先读取指定 skill 文件核对要求，然后输出。"}}',
            '{"type":"item.completed","item":{"id":"item_2","type":"agent_message",'
            '"text":"# 专利文件检查报告\\n\\n## 第一阶段：权利要求书检查与特征分解\\n最终报告"}}',
            '{"type":"turn.completed","usage":{"input_tokens":10,"output_tokens":5}}',
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

    assert result.content.startswith("# 专利文件检查报告")
    snapshots = [
        event.content
        for event in captured_events
        if event.event_type == "report_snapshot"
    ]
    assert snapshots == [
        "# 专利文件检查报告\n\n## 第一阶段：权利要求书检查与特征分解\n最终报告"
    ]


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


@pytest.mark.parametrize("prefix", ["", "printf 'partial JSON without newline'\n"])
def test_codex_client_enforces_timeout_while_stdout_pipe_is_open(tmp_path: Path, prefix) -> None:
    skill = tmp_path / "check-patent.md"
    skill.write_text("# 专利检查 Skill", encoding="utf-8")
    script = tmp_path / "slow-codex"
    script.write_text(f"#!/bin/sh\n{prefix}sleep 5\n", encoding="utf-8")
    script.chmod(script.stat().st_mode | stat.S_IXUSR)
    client = CodexClient(
        Settings(
            app_secret_key="test-secret-key-with-at-least-32-bytes",
            codex_skill_path=skill,
            codex_command=str(script),
            codex_timeout_seconds=1,
        )
    )
    started_at = time.perf_counter()

    with pytest.raises(UserFacingError, match="Codex 执行超时"):
        client.run(stage="stage_one", prompt="请审查。", on_event=lambda event: None)

    assert time.perf_counter() - started_at < 3


def test_codex_client_delivers_buffered_events_before_process_finishes(tmp_path: Path) -> None:
    skill = tmp_path / "SKILL.md"
    skill.write_text("# 审查")
    script = tmp_path / "burst-codex"
    script.write_text(
        "#!/bin/sh\nprintf '%s\\n' "
        "'{\"type\":\"turn.started\"}' '{\"type\":\"turn.completed\"}'\nsleep 5\n"
    )
    script.chmod(0o700)
    events = []
    client = CodexClient(Settings(
        codex_command=str(script), codex_skill_path=skill, codex_timeout_seconds=1,
    ))
    with pytest.raises(UserFacingError, match="Codex 执行超时"):
        client.run("stage_one", "审查", events.append)
    assert [e.event_type for e in events] == ["turn.started", "turn.completed"]


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


def test_task_environment_excludes_application_credentials(tmp_path, monkeypatch):
    import tomllib

    monkeypatch.setenv("DATABASE_URL", "postgresql://private-database")
    monkeypatch.setenv("APP_SECRET_KEY", "private-app-secret")
    monkeypatch.setenv("CODEX_API_KEY", "unrelated-inherited-key")
    client = CodexClient(
        Settings(gpt_api_key="configured-model-key"), workspace=tmp_path, isolated=True
    )
    env = client._build_environment()
    assert "DATABASE_URL" not in env and "APP_SECRET_KEY" not in env
    assert env["CODEX_API_KEY"] == "configured-model-key"
    assert env["HOME"] == str(tmp_path)
    config = tomllib.loads((tmp_path / ".codex/config.toml").read_text())
    policy = config["permissions"][config["default_permissions"]]
    assert policy["filesystem"][":root"] == "deny"
    assert policy["filesystem"][str(tmp_path)] == "write"
    assert policy["network"]["enabled"] is False
    assert "--sandbox" not in client._build_command()
