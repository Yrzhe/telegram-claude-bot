"""Skills API routes."""

import logging
from typing import List, Optional
from pathlib import Path

from fastapi import APIRouter, HTTPException, status, Depends
from pydantic import BaseModel

from ..dependencies import get_current_user_id, get_skill_manager

logger = logging.getLogger(__name__)

router = APIRouter()


class SkillItem(BaseModel):
    """Skill summary."""
    name: str
    description: str


class SkillListResponse(BaseModel):
    """List of installed skills."""
    skills: List[SkillItem]
    count: int


class SkillDetailResponse(BaseModel):
    """Skill detail with content."""
    name: str
    description: str
    content: str
    files: List[str]


@router.get("", response_model=SkillListResponse)
async def list_skills(
    user_id: int = Depends(get_current_user_id),
    skill_manager=Depends(get_skill_manager)
):
    """List all installed skills for the current user."""
    if skill_manager is None:
        return SkillListResponse(skills=[], count=0)

    user_skills = skill_manager.get_user_skills(user_id)
    skills = [
        SkillItem(name=s.name, description=s.description)
        for s in user_skills
    ]
    return SkillListResponse(skills=skills, count=len(skills))


@router.get("/{name}", response_model=SkillDetailResponse)
async def get_skill(
    name: str,
    user_id: int = Depends(get_current_user_id),
    skill_manager=Depends(get_skill_manager)
):
    """Get skill detail including SKILL.md content and file tree."""
    if skill_manager is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Skill not found"
        )

    skill = skill_manager.get_skill(user_id, name)
    if skill is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Skill not found"
        )

    content = skill.get_content()

    # Collect relative file paths within the skill directory
    files = []
    for f in sorted(skill.path.rglob("*")):
        if f.is_file():
            files.append(str(f.relative_to(skill.path)))

    return SkillDetailResponse(
        name=skill.name,
        description=skill.description,
        content=content,
        files=files
    )


@router.delete("/{name}")
async def delete_skill(
    name: str,
    user_id: int = Depends(get_current_user_id),
    skill_manager=Depends(get_skill_manager)
):
    """Delete an installed skill."""
    if skill_manager is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Skill not found"
        )

    success = skill_manager.delete_skill(user_id, name)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Skill not found"
        )

    logger.info(f"User {user_id} deleted skill '{name}'")
    return {"success": True}
