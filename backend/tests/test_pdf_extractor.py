"""这个文件用于验证 PDF 文本抽取服务的关键错误映射。"""

from pathlib import Path

import pytest

from app.services.errors import UserFacingError
from app.services.pdf_extractor import extract_pdf_text


def test_extract_pdf_text_rejects_invalid_pdf(tmp_path: Path) -> None:
    path = tmp_path / "broken.pdf"
    path.write_bytes(b"not a pdf")

    with pytest.raises(UserFacingError, match="文件文本抽取失败"):
        extract_pdf_text(path)
