"""这个文件用于定义可安全返回给前端的业务异常。"""


class UserFacingError(Exception):
    """Exception whose message is safe to show to the current user."""

    def __init__(self, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code
