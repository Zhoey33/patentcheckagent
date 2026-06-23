"""这个文件用于验证后端配置默认值和环境变量覆盖行为。"""


from app.core.config import Settings


def test_settings_exposes_file_limits() -> None:
    settings = Settings(max_file_size_mb=20, max_task_files=4, max_total_text_chars=200000)

    assert settings.max_file_size_bytes == 20 * 1024 * 1024
    assert settings.max_task_files == 4
    assert settings.max_total_text_chars == 200000


def test_settings_reads_gpt_environment(monkeypatch) -> None:
    monkeypatch.setenv("GPT_BASE_URL", "https://example.test")
    monkeypatch.setenv("GPT_API_KEY", "test-key")
    monkeypatch.setenv("GPT_MODEL", "gpt-5.5")

    settings = Settings()

    assert settings.gpt_base_url == "https://example.test"
    assert settings.gpt_api_key == "test-key"
    assert settings.gpt_model == "gpt-5.5"
