"""这个文件用于定义专利审查任务接口的数据结构。"""

from datetime import datetime

from pydantic import BaseModel


class PatentCheckFileRead(BaseModel):
    id: str
    file_role: str
    original_filename: str
    content_type: str | None
    file_size_bytes: int
    extracted_text_length: int
    extraction_status: str
    extraction_error: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class PatentCheckTaskRead(BaseModel):
    id: str
    title: str
    technical_field: str | None
    status: str
    claims_text_length: int
    specification_text_length: int
    drawings_text_length: int
    abstract_text_length: int
    input_cleanup_status: str
    error_message: str | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    files: list[PatentCheckFileRead] = []

    model_config = {"from_attributes": True}


class PatentCheckTaskList(BaseModel):
    items: list[PatentCheckTaskRead]
    total: int
    page: int
    page_size: int


class PatentCheckReportRead(BaseModel):
    id: str
    status: str
    final_report: str | None
    error_message: str | None
