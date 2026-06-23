"""这个文件用于定义管理员接口的请求和响应数据结构。"""

from pydantic import BaseModel, Field

from app.schemas.auth import UserRead
from app.schemas.patent_check import PatentCheckTaskRead


class AdminUserList(BaseModel):
    items: list[UserRead]
    total: int


class AdminUserCreate(BaseModel):
    username: str = Field(min_length=2, max_length=64)
    password: str = Field(min_length=8, max_length=128)
    role: str = Field(default="user", pattern="^(user|admin)$")
    is_active: bool = True


class AdminUserUpdate(BaseModel):
    role: str | None = Field(default=None, pattern="^(user|admin)$")
    is_active: bool | None = None


class AdminPasswordReset(BaseModel):
    password: str = Field(min_length=8, max_length=128)


class AdminTaskList(BaseModel):
    items: list[PatentCheckTaskRead]
    total: int
    page: int
    page_size: int
