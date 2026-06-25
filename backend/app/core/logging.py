"""这个文件用于配置后端和 Worker 的统一安全日志格式。"""

import logging

from app.core.config import Settings


def configure_logging(settings: Settings) -> None:
    """Configure process-wide logging without exposing secrets or document text."""

    level = getattr(logging, settings.log_level.upper(), logging.INFO)
    root_logger = logging.getLogger()
    if root_logger.handlers:
        root_logger.setLevel(level)
        return
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )
