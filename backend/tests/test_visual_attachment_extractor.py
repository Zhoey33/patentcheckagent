"""这个文件用于验证上传专利文件中的图片附件提取逻辑。"""

import zipfile
from pathlib import Path

from app.models.patent_check_file import PatentCheckFile
from app.services.visual_attachment_extractor import collect_visual_attachments


def test_collect_visual_attachments_extracts_docx_media(tmp_path: Path) -> None:
    docx_path = tmp_path / "drawings.docx"
    png_bytes = b"\x89PNG\r\n\x1a\nfake-image-bytes"
    with zipfile.ZipFile(docx_path, "w") as archive:
        archive.writestr("word/document.xml", "<document />")
        archive.writestr("word/media/image1.png", png_bytes)

    uploaded_file = PatentCheckFile(
        file_role="drawings",
        original_filename="drawings.docx",
        stored_path=str(docx_path),
        content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        file_size_bytes=docx_path.stat().st_size,
        extracted_text_length=0,
        extraction_status="text_unavailable",
    )

    images = collect_visual_attachments([uploaded_file], tmp_path / "visuals")

    assert len(images) == 1
    assert images[0].name == "drawings-image-1.png"
    assert images[0].read_bytes() == png_bytes


def test_collect_visual_attachments_prioritizes_dedicated_drawings(
    tmp_path: Path,
) -> None:
    specification_docx = tmp_path / "specification.docx"
    drawings_docx = tmp_path / "drawings.docx"
    with zipfile.ZipFile(specification_docx, "w") as archive:
        archive.writestr("word/media/spec.png", b"spec-image")
    with zipfile.ZipFile(drawings_docx, "w") as archive:
        archive.writestr("word/media/drawing.png", b"drawing-image")

    specification_file = PatentCheckFile(
        file_role="specification",
        original_filename="specification.docx",
        stored_path=str(specification_docx),
        content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        file_size_bytes=specification_docx.stat().st_size,
        extracted_text_length=0,
        extraction_status="succeeded",
    )
    drawing_file = PatentCheckFile(
        file_role="drawings",
        original_filename="drawings.docx",
        stored_path=str(drawings_docx),
        content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        file_size_bytes=drawings_docx.stat().st_size,
        extracted_text_length=0,
        extraction_status="text_unavailable",
    )

    images = collect_visual_attachments(
        [specification_file, drawing_file],
        tmp_path / "visuals",
        max_images=1,
    )

    assert len(images) == 1
    assert images[0].read_bytes() == b"drawing-image"
