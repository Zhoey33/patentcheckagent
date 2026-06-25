"""这个文件用于封装 GPT-5.5 兼容接口调用、重试和错误映射。"""

import logging
import time
from dataclasses import dataclass

import httpx

from app.core.config import Settings
from app.services.errors import UserFacingError

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ModelCallResult:
    content: str
    input_tokens: int | None
    output_tokens: int | None
    latency_ms: int


class ModelClient:
    """OpenAI-compatible chat completions client."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def chat(self, messages: list[dict[str, str]]) -> ModelCallResult:
        """Call the configured GPT model and return Markdown content."""

        if not self.settings.gpt_api_key:
            raise UserFacingError("模型 API key 未配置，请联系系统管理员。", status_code=500)

        last_error: Exception | None = None
        for attempt in range(self.settings.gpt_max_retries + 1):
            started_at = time.perf_counter()
            attempt_number = attempt + 1
            try:
                logger.info(
                    "model_call_attempt_started model=%s attempt=%s max_attempts=%s",
                    self.settings.gpt_model,
                    attempt_number,
                    self.settings.gpt_max_retries + 1,
                )
                with httpx.Client(
                    base_url=self.settings.gpt_base_url,
                    timeout=self.settings.gpt_timeout_seconds,
                    headers={"Authorization": f"Bearer {self.settings.gpt_api_key}"},
                ) as client:
                    response = client.post(
                        "/v1/chat/completions",
                        json={
                            "model": self.settings.gpt_model,
                            "messages": messages,
                            "temperature": 0.1,
                        },
                    )
                latency_ms = int((time.perf_counter() - started_at) * 1000)
                response.raise_for_status()
                payload = response.json()
                content = payload["choices"][0]["message"]["content"]
                usage = payload.get("usage") or {}
                logger.info(
                    "model_call_attempt_succeeded model=%s attempt=%s latency_ms=%s status_code=%s",
                    self.settings.gpt_model,
                    attempt_number,
                    latency_ms,
                    response.status_code,
                )
                return ModelCallResult(
                    content=content,
                    input_tokens=usage.get("prompt_tokens"),
                    output_tokens=usage.get("completion_tokens"),
                    latency_ms=latency_ms,
                )
            except httpx.TimeoutException as exc:
                last_error = exc
                logger.warning(
                    "model_call_attempt_failed model=%s attempt=%s error_type=%s",
                    self.settings.gpt_model,
                    attempt_number,
                    type(exc).__name__,
                )
            except httpx.HTTPStatusError as exc:
                last_error = exc
                logger.warning(
                    "model_call_attempt_failed model=%s attempt=%s error_type=%s status_code=%s",
                    self.settings.gpt_model,
                    attempt_number,
                    type(exc).__name__,
                    exc.response.status_code,
                )
                if 400 <= exc.response.status_code < 500:
                    break
            except httpx.RequestError as exc:
                last_error = exc
                logger.warning(
                    "model_call_attempt_failed model=%s attempt=%s error_type=%s",
                    self.settings.gpt_model,
                    attempt_number,
                    type(exc).__name__,
                )
            except (KeyError, IndexError, TypeError, ValueError) as exc:
                last_error = exc
                logger.warning(
                    "model_call_attempt_failed model=%s attempt=%s error_type=%s",
                    self.settings.gpt_model,
                    attempt_number,
                    type(exc).__name__,
                )
                break

            if attempt < self.settings.gpt_max_retries:
                time.sleep(1 + attempt)

        if isinstance(last_error, httpx.TimeoutException):
            raise UserFacingError("模型调用超时，请稍后重试。", status_code=504) from last_error
        raise UserFacingError("模型服务暂不可用，请稍后重试。", status_code=502) from last_error
