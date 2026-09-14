"""Skill 管理及可选 skill 的接口结构。"""

from datetime import datetime

from pydantic import BaseModel, Field


class SkillWrite(BaseModel):
    display_name: str = Field(min_length=1, max_length=128)
    files: dict[str, str]
    is_enabled: bool = True


class SkillUpdate(SkillWrite):
    version: int = Field(ge=1)


class SkillSummary(BaseModel):
    id: str
    name: str
    display_name: str
    description: str
    version: int
    is_enabled: bool
    is_default: bool
    updated_at: datetime

    model_config = {"from_attributes": True}


class SkillRead(SkillSummary):
    files: dict[str, str]


class SkillList(BaseModel):
    items: list[SkillSummary]
