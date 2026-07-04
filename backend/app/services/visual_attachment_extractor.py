"""这个文件用于把专利附图文件转换为可传给 Codex 的图片附件。"""

import shutil
import zipfile
from pathlib import Path

import fitz

from app.models.patent_check_file import PatentCheckFile

VISUAL_FILE_ROLES = {"drawings", "specification"}
VISUAL_FILE_ROLE_PRIORITY = {"drawings": 0, "specification": 1}
SUPPORTED_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp"}
MAX_VISUAL_ATTACHMENTS = 8


def collect_visual_attachments(
    files: list[PatentCheckFile],
    output_dir: Path,
    max_images: int = MAX_VISUAL_ATTACHMENTS,
) -> list[Path]:
    """Extract or render uploaded visual material into image files for Codex."""

    output_dir.mkdir(parents=True, exist_ok=True)
    images: list[Path] = []
    for file in sorted(files, key=visual_file_priority):
        if file.file_role not in VISUAL_FILE_ROLES or not file.stored_path:
            continue
        path = Path(file.stored_path)
        if not path.exists():
            continue
        remaining = max_images - len(images)
        if remaining <= 0:
            break
        images.extend(extract_visuals_from_path(path, output_dir, file.file_role, remaining))
    return images[:max_images]


def visual_file_priority(file: PatentCheckFile) -> tuple[int, str]:
    """Return collection priority so dedicated drawings are attached first."""

    return (VISUAL_FILE_ROLE_PRIORITY.get(file.file_role, 99), file.original_filename)


def extract_visuals_from_path(
    path: Path,
    output_dir: Path,
    role: str,
    max_images: int,
) -> list[Path]:
    """Extract visual attachments from one uploaded PDF or Word document."""

    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return render_pdf_pages(path, output_dir, role, max_images)
    if suffix == ".docx":
        return extract_docx_images(path, output_dir, role, max_images)
    return []


def render_pdf_pages(path: Path, output_dir: Path, role: str, max_pages: int) -> list[Path]:
    """Render PDF pages as PNG images for visual review."""

    images: list[Path] = []
    document = fitz.open(path)
    try:
        matrix = fitz.Matrix(1.5, 1.5)
        for index, page in enumerate(document):
            if len(images) >= max_pages:
                break
            pixmap = page.get_pixmap(matrix=matrix, alpha=False)
            image_path = output_dir / f"{role}-page-{index + 1}.png"
            pixmap.save(image_path)
            images.append(image_path)
    finally:
        document.close()
    return images


def extract_docx_images(path: Path, output_dir: Path, role: str, max_images: int) -> list[Path]:
    """Extract embedded Word media images into standalone files."""

    images: list[Path] = []
    with zipfile.ZipFile(path) as archive:
        media_names = [
            name
            for name in archive.namelist()
            if name.startswith("word/media/")
            and Path(name).suffix.lower() in SUPPORTED_IMAGE_SUFFIXES
        ]
        for index, name in enumerate(media_names[:max_images], start=1):
            suffix = Path(name).suffix.lower()
            image_path = output_dir / f"{role}-image-{index}{suffix}"
            with archive.open(name) as source, image_path.open("wb") as target:
                shutil.copyfileobj(source, target)
            images.append(image_path)
    return images
