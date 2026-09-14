"""登录用户选用 skill，管理员维护 skill 包。"""

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Response
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.deps import get_current_admin, get_current_user
from app.models.review_skill import ReviewSkill
from app.models.user import User
from app.schemas.review_skill import SkillList, SkillRead, SkillUpdate, SkillWrite
from app.services.errors import UserFacingError
from app.services.skill_service import ensure_default_skill, validate_skill_files

router = APIRouter(tags=["skills"])


@router.get("/api/skills", response_model=SkillList)
def available_skills(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    ensure_default_skill(db)
    return {
        "items": db.scalars(
            select(ReviewSkill)
            .where(ReviewSkill.is_enabled.is_(True))
            .order_by(ReviewSkill.is_default.desc(), ReviewSkill.name)
        ).all()
    }


@router.get("/api/admin/skills", response_model=SkillList)
def list_skills(db: Session = Depends(get_db), _: User = Depends(get_current_admin)):
    ensure_default_skill(db)
    return {
        "items": db.scalars(
            select(ReviewSkill).order_by(
                ReviewSkill.is_default.desc(), ReviewSkill.updated_at.desc()
            )
        ).all()
    }


def get_skill(db: Session, skill_id: str) -> ReviewSkill:
    skill = db.get(ReviewSkill, skill_id)
    if skill is None:
        raise UserFacingError("Skill 不存在。", 404)
    return skill


def commit_skill(db: Session) -> None:
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise UserFacingError("Skill 名称或默认设置冲突，请刷新后重试。", 409) from exc


@router.get("/api/admin/skills/{skill_id}", response_model=SkillRead)
def read_skill(skill_id: str, db: Session = Depends(get_db), _: User = Depends(get_current_admin)):
    return get_skill(db, skill_id)


@router.post("/api/admin/skills", response_model=SkillRead)
def create_skill(
    payload: SkillWrite, db: Session = Depends(get_db), _: User = Depends(get_current_admin)
):
    name, description = validate_skill_files(payload.files)
    skill = ReviewSkill(
        name=name,
        display_name=payload.display_name.strip() or name,
        description=description,
        files=payload.files,
        is_enabled=payload.is_enabled,
    )
    db.add(skill)
    commit_skill(db)
    db.refresh(skill)
    return skill


@router.put("/api/admin/skills/{skill_id}", response_model=SkillRead)
def update_skill(
    skill_id: str,
    payload: SkillUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_admin),
):
    skill = get_skill(db, skill_id)
    name, description = validate_skill_files(payload.files)
    if skill.is_default and not payload.is_enabled:
        raise UserFacingError("请先将另一个已启用的 Skill 设为默认，再停用此项。")
    changed = db.execute(
        update(ReviewSkill)
        .where(ReviewSkill.id == skill_id, ReviewSkill.version == payload.version)
        .values(
            name=name,
            display_name=payload.display_name.strip() or name,
            description=description,
            files=payload.files,
            is_enabled=payload.is_enabled,
            version=payload.version + 1,
            updated_at=datetime.now(UTC),
        )
    )
    if changed.rowcount != 1:
        db.rollback()
        raise UserFacingError("Skill 已被更新，请重新打开后编辑。", 409)
    commit_skill(db)
    db.refresh(skill)
    return skill


@router.post("/api/admin/skills/{skill_id}/default", response_model=SkillRead)
def set_default_skill(
    skill_id: str, db: Session = Depends(get_db), _: User = Depends(get_current_admin)
):
    skill = get_skill(db, skill_id)
    if not skill.is_enabled:
        raise UserFacingError("请先启用此 Skill。")
    db.execute(update(ReviewSkill).where(ReviewSkill.is_default.is_(True)).values(is_default=False))
    db.flush()
    skill.is_default = True
    commit_skill(db)
    db.refresh(skill)
    return skill


@router.delete("/api/admin/skills/{skill_id}", status_code=204)
def delete_skill(
    skill_id: str, db: Session = Depends(get_db), _: User = Depends(get_current_admin)
):
    skill = get_skill(db, skill_id)
    if skill.is_default:
        raise UserFacingError("请先将另一个 Skill 设为默认，再删除此项。")
    db.delete(skill)
    db.commit()
    return Response(status_code=204)
