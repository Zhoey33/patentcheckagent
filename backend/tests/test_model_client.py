"""这个文件用于验证模型客户端的错误映射和安全日志行为。"""

import logging

import httpx
import pytest

from app.core.config import Settings
from app.services.errors import UserFacingError
from app.services.model_client import ModelClient


class FailingHttpClient:
    """Test double that raises a transport error from the chat completion call."""

    def __init__(self, *args, **kwargs) -> None:
        pass

    def __enter__(self):
        return self

    def __exit__(self, *args) -> None:
        return None

    def post(self, *args, **kwargs):
        request = httpx.Request("POST", "https://example.test/v1/chat/completions")
        raise httpx.ConnectError("connection refused", request=request)


def test_model_client_maps_transport_errors_to_user_facing_error(monkeypatch, caplog) -> None:
    monkeypatch.setattr("app.services.model_client.httpx.Client", FailingHttpClient)
    settings = Settings(
        app_secret_key="test-secret-key-with-at-least-32-bytes",
        gpt_api_key="test-api-key",
        gpt_base_url="https://example.test",
        gpt_max_retries=0,
    )
    client = ModelClient(settings)

    with caplog.at_level(logging.WARNING):
        with pytest.raises(UserFacingError, match="模型服务暂不可用"):
            client.chat([{"role": "user", "content": "hello"}])

    assert "model_call_attempt_failed" in caplog.text
    assert "test-api-key" not in caplog.text
