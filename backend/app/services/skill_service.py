"""校验、初始化和快照化审查 skill；不解析用户的专利材料。"""

import re
from copy import deepcopy
from pathlib import Path, PurePosixPath

import yaml
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.review_skill import ReviewSkill
from app.services.errors import UserFacingError

BUILTIN_SKILL_PATH = Path(__file__).resolve().parents[2] / "skills" / "check-patent"
if not BUILTIN_SKILL_PATH.is_dir():
    BUILTIN_SKILL_PATH = Path(__file__).resolve().parents[3] / "skills" / "check-patent"


def validate_skill_files(files: dict[str, str]) -> tuple[str, str]:
    if not files or len(files) > 32 or "SKILL.md" not in files:
        raise UserFacingError("Skill 必须包含 SKILL.md，最多 32 个 Markdown 文件。")
    if sum(len(content.encode("utf-8")) for content in files.values()) > 512_000:
        raise UserFacingError("Skill 文件总大小不能超过 500 KB。")
    for name in files:
        path = PurePosixPath(name)
        if (name != "SKILL.md" and not name.startswith("references/")) or (
            path.is_absolute()
            or ".." in path.parts
            or str(path) != name
            or "\\" in name
            or path.suffix != ".md"
            or len(name) > 160
        ):
            raise UserFacingError("仅支持 SKILL.md 和 references/ 下的 Markdown 文件。")
    match = re.match(r"\A---\r?\n(.*?)\r?\n---\r?\n(.+)\Z", files["SKILL.md"], re.S)
    if not match:
        raise UserFacingError("SKILL.md 须包含 YAML 头部（name、description）和正文。")
    try:
        metadata = yaml.safe_load(match[1])
    except yaml.YAMLError as exc:
        raise UserFacingError("SKILL.md 的 YAML 头部格式错误。") from exc
    name = metadata.get("name") if isinstance(metadata, dict) else None
    description = metadata.get("description") if isinstance(metadata, dict) else None
    if (
        not isinstance(name, str)
        or not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", name)
        or len(name) > 64
    ):
        raise UserFacingError("Skill 的 name 须为最多 64 位小写字母、数字和连字符。")
    if not isinstance(description, str) or not 1 <= len(description.strip()) <= 1024:
        raise UserFacingError("Skill 的 description 须为 1–1024 个字符。")
    if not match[2].strip():
        raise UserFacingError("Skill 正文不能为空。")
    return name, description.strip()


def builtin_skill_files() -> dict[str, str]:
    return {
        str(path.relative_to(BUILTIN_SKILL_PATH)): path.read_text(encoding="utf-8")
        for path in sorted(BUILTIN_SKILL_PATH.rglob("*.md"))
    }


def ensure_default_skill(db: Session) -> None:
    """仅在首次初始化空表时写入内置 skill，不覆盖管理员编辑。"""
    if db.scalar(select(ReviewSkill.id).limit(1)):
        return
    files = builtin_skill_files()
    name, description = validate_skill_files(files)
    db.add(
        ReviewSkill(
            name=name,
            display_name="专利文件检查",
            description=description,
            files=files,
            is_default=True,
        )
    )
    db.commit()


def snapshot_skill(db: Session, skill_id: str | None) -> dict:
    ensure_default_skill(db)
    query = select(ReviewSkill).where(ReviewSkill.is_enabled.is_(True))
    query = (
        query.where(ReviewSkill.id == skill_id)
        if skill_id
        else query.where(ReviewSkill.is_default.is_(True))
    )
    skill = db.scalar(query)
    if skill is None:
        raise UserFacingError("所选 Skill 不存在或已停用，请重新选择。")
    return {
        "id": skill.id,
        "name": skill.name,
        "display_name": skill.display_name,
        "version": skill.version,
        "files": deepcopy(skill.files),
    }


def materialize_skill(snapshot: dict, workspace: Path) -> Path:
    """把任务提交时的 skill 快照放到 Codex 可发现的目录。"""
    name, _ = validate_skill_files(snapshot["files"])
    root = workspace / ".agents" / "skills" / name
    for relative, content in snapshot["files"].items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    return root / "SKILL.md"
