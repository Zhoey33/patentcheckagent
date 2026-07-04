"""这个文件用于验证后端配置默认值和环境变量覆盖行为。"""


from app.core.config import Settings


def test_settings_exposes_file_limits() -> None:
    settings = Settings(max_file_size_mb=20, max_task_files=4, max_total_text_chars=200000)

    assert settings.max_file_size_bytes == 20 * 1024 * 1024
    assert settings.max_task_files == 4
    assert settings.max_total_text_chars == 200000


def test_settings_reads_codex_environment(monkeypatch) -> None:
    monkeypatch.setenv("CODEX_COMMAND", "/usr/local/bin/codex")
    monkeypatch.setenv("CODEX_SKILL_PATH", "skills/custom.md")
    monkeypatch.setenv("CODEX_TIMEOUT_SECONDS", "900")
    monkeypatch.setenv("CODEX_MODEL", "gpt-5.5")

    settings = Settings()

    assert settings.codex_command == "/usr/local/bin/codex"
    assert str(settings.codex_skill_path) == "skills/custom.md"
    assert settings.codex_timeout_seconds == 900
    assert settings.codex_model == "gpt-5.5"
