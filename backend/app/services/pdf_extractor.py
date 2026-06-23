"""这个文件用于从可复制文本型 PDF 中抽取审查文本。"""

from pathlib import Path

from pypdf import PdfReader

from app.services.errors import UserFacingError


def extract_pdf_text(path: Path) -> str:
    """Extract text from a text-based PDF file."""

    try:
        reader = PdfReader(str(path))
        pages = [page.extract_text() or "" for page in reader.pages]
    except Exception as exc:
        raise UserFacingError("文件文本抽取失败，请确认 PDF 文件未损坏。") from exc

    text = "\n\n".join(page.strip() for page in pages if page.strip()).strip()
    if not text:
        raise UserFacingError("未能抽取到可复制文本，请上传可复制文本型 PDF，暂不支持扫描件 OCR。")
    return text
