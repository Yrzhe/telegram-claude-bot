"""Skill Manager - Manages user-uploaded skills"""

import logging
import re
import shutil
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

from .validator import SkillValidator, SkillValidationResult

logger = logging.getLogger(__name__)


def _parse_yaml_description(content: str) -> str:
    """Parse description from YAML frontmatter, handling multiline syntaxes (>, |, quoted)."""
    # Try single-line first: description: some text
    m = re.search(r'^description:\s*([^>\|"\'\n].+)$', content, re.MULTILINE)
    if m:
        return m.group(1).strip().strip('"').strip("'")

    # Folded (>) or literal (|) block scalar
    m = re.search(r'^description:\s*[>\|]-?\s*\n((?:[ \t]+.+\n?)+)', content, re.MULTILINE)
    if m:
        lines = m.group(1).split('\n')
        parts = [line.strip() for line in lines if line.strip()]
        return ' '.join(parts)

    # Quoted multiline
    m = re.search(r'^description:\s*"([^"]+)"', content, re.MULTILINE | re.DOTALL)
    if m:
        return ' '.join(m.group(1).split())

    return ""


@dataclass
class UserSkill:
    """Represents an installed user skill"""
    name: str
    description: str
    path: Path

    def get_content(self) -> str:
        """Read the SKILL.md content"""
        skill_md = self.path / "SKILL.md"
        if skill_md.exists():
            return skill_md.read_text(encoding='utf-8')
        return ""


class SkillManager:
    """
    Manages user-uploaded skills.

    Skills are stored in: users/<user_id>/skills/<skill-name>/
    """

    def __init__(self, users_base_path: str, system_skills_path: str = None):
        """
        Initialize SkillManager.

        Args:
            users_base_path: Base path for user data directories
            system_skills_path: Path to system-wide skills directory (.claude/skills)
        """
        self.users_base_path = Path(users_base_path)
        self.system_skills_path = Path(system_skills_path) if system_skills_path else None
        self.validator = SkillValidator()

    def _get_user_skills_dir(self, user_id: int) -> Path:
        """Get the skills directory for a user"""
        skills_dir = self.users_base_path / str(user_id) / "skills"
        skills_dir.mkdir(parents=True, exist_ok=True)
        return skills_dir

    def get_user_skills(self, user_id: int) -> List[UserSkill]:
        """Get all installed skills for a user"""
        skills_dir = self._get_user_skills_dir(user_id)
        skills = []

        for skill_dir in skills_dir.iterdir():
            if not skill_dir.is_dir():
                continue

            skill_md = skill_dir / "SKILL.md"
            if not skill_md.exists():
                continue

            # Parse skill info
            content = skill_md.read_text(encoding='utf-8')
            name = skill_dir.name
            description = _parse_yaml_description(content)

            skills.append(UserSkill(
                name=name,
                description=description,
                path=skill_dir
            ))

        return skills

    def get_skill(self, user_id: int, skill_name: str) -> Optional[UserSkill]:
        """Get a specific skill by name"""
        skills = self.get_user_skills(user_id)
        for skill in skills:
            if skill.name == skill_name:
                return skill
        return None

    def check_skill_conflicts(self, user_id: int, skill_name: str) -> dict:
        """Check if a skill name conflicts with system or user skills.

        Returns:
            {"system": bool, "user": bool} indicating where conflicts exist.
        """
        conflicts = {"system": False, "user": False}

        # Check system skills
        if self.system_skills_path and (self.system_skills_path / skill_name).exists():
            conflicts["system"] = True

        # Check user skills
        user_skills_dir = self._get_user_skills_dir(user_id)
        if (user_skills_dir / skill_name).exists():
            conflicts["user"] = True

        return conflicts

    def install_skill_from_zip(
        self,
        user_id: int,
        zip_path: Path,
        skip_validation: bool = False,
        rename_to: str = None,
        overwrite: bool = False
    ) -> tuple[bool, str, Optional[SkillValidationResult]]:
        """
        Install a skill from a zip file.

        Args:
            user_id: User ID
            zip_path: Path to the uploaded zip file

        Returns:
            (success, message, validation_result)
        """
        # Create temp directory for extraction
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)

            # Extract zip
            try:
                with zipfile.ZipFile(zip_path, 'r') as zf:
                    # Security check: no absolute paths or path traversal
                    for name in zf.namelist():
                        if name.startswith('/') or '..' in name:
                            return False, f"Security error: invalid path in zip: {name}", None
                    zf.extractall(temp_path)
            except zipfile.BadZipFile:
                return False, "Invalid zip file", None
            except Exception as e:
                return False, f"Failed to extract zip: {e}", None

            # Find the skill directory (might be nested)
            skill_dir = self._find_skill_dir(temp_path)
            if not skill_dir:
                return False, "No SKILL.md found in zip. Please include a SKILL.md file.", None

            # Validate the skill
            result = self.validator.validate_skill_directory(skill_dir)

            if not result.is_valid and not skip_validation:
                return False, "Skill validation failed", result

            if not result.is_valid and skip_validation:
                logger.warning(f"Admin force-installing skill with validation errors for user {user_id}")

            # Determine final skill name
            skill_name = rename_to if rename_to else result.skill_name
            user_skills_dir = self._get_user_skills_dir(user_id)
            target_dir = user_skills_dir / skill_name

            # Check conflicts
            conflicts = self.check_skill_conflicts(user_id, skill_name)

            if conflicts["system"] and not overwrite:
                return False, f"CONFLICT_SYSTEM:{skill_name}", result

            if conflicts["user"] and not overwrite:
                return False, f"CONFLICT_USER:{skill_name}", result

            if target_dir.exists():
                shutil.rmtree(target_dir)
                logger.info(f"Updating existing skill: {skill_name}")

            # Copy skill to user's skills directory
            shutil.copytree(skill_dir, target_dir)

            # If renamed, update the name in SKILL.md frontmatter
            if rename_to and rename_to != result.skill_name:
                skill_md = target_dir / "SKILL.md"
                content = skill_md.read_text(encoding='utf-8')
                content = re.sub(
                    r'^name:\s*.+$',
                    f'name: {rename_to}',
                    content,
                    count=1,
                    flags=re.MULTILINE
                )
                skill_md.write_text(content, encoding='utf-8')

            logger.info(f"Installed skill '{skill_name}' for user {user_id}")

            return True, f"Skill '{skill_name}' installed successfully!", result

    def _find_skill_dir(self, base_path: Path) -> Optional[Path]:
        """Find the directory containing SKILL.md"""
        # Check if SKILL.md is directly in base_path
        if (base_path / "SKILL.md").exists():
            return base_path

        # Check one level deep (common: zip contains a folder)
        for item in base_path.iterdir():
            if item.is_dir():
                if (item / "SKILL.md").exists():
                    return item

        # Search recursively as last resort
        for skill_md in base_path.rglob("SKILL.md"):
            return skill_md.parent

        return None

    def delete_skill(self, user_id: int, skill_name: str) -> bool:
        """Delete a user's skill"""
        skills_dir = self._get_user_skills_dir(user_id)
        skill_dir = skills_dir / skill_name

        if not skill_dir.exists():
            return False

        try:
            shutil.rmtree(skill_dir)
            logger.info(f"Deleted skill '{skill_name}' for user {user_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to delete skill: {e}")
            return False

    def share_skill(self, user_id: int, skill_name: str) -> tuple[bool, str]:
        """Copy a user's skill to the system skills directory so all users can use it."""
        if not self.system_skills_path:
            return False, "System skills path not configured"

        skill = self.get_skill(user_id, skill_name)
        if not skill:
            return False, f"Skill '{skill_name}' not found"

        target_dir = self.system_skills_path / skill_name
        if target_dir.exists():
            shutil.rmtree(target_dir)

        shutil.copytree(skill.path, target_dir)
        logger.info(f"Shared skill '{skill_name}' from user {user_id} to system skills")
        return True, f"Skill '{skill_name}' shared to all users"

    def unshare_skill(self, skill_name: str, admin_user_id: int = None) -> tuple[bool, str]:
        """Move a skill from system directory back to admin's private skills."""
        if not self.system_skills_path:
            return False, "System skills path not configured"

        source_dir = self.system_skills_path / skill_name
        if not source_dir.exists():
            return False, f"System skill '{skill_name}' not found"

        # Move to admin's private skills if admin_user_id provided
        if admin_user_id:
            user_skills_dir = self._get_user_skills_dir(admin_user_id)
            target_dir = user_skills_dir / skill_name
            if target_dir.exists():
                shutil.rmtree(target_dir)
            shutil.copytree(source_dir, target_dir)
            logger.info(f"Moved system skill '{skill_name}' to admin {admin_user_id}'s private skills")

        shutil.rmtree(source_dir)
        logger.info(f"Unshared system skill '{skill_name}'")
        return True, f"Skill '{skill_name}' moved from system to your private skills"

    def list_system_skills(self) -> list[str]:
        """List all system-wide skill names."""
        if not self.system_skills_path or not self.system_skills_path.exists():
            return []
        return sorted([
            d.name for d in self.system_skills_path.iterdir()
            if d.is_dir() and (d / "SKILL.md").exists()
        ])

    def get_skills_for_agent(self, user_id: int) -> str:
        """
        Get skills content formatted for Agent system prompt.

        Returns a string that can be appended to the system prompt.
        """
        skills = self.get_user_skills(user_id)
        if not skills:
            return ""

        lines = ["\n\n## User Custom Skills\n"]
        lines.append("The user has installed the following custom skills:\n")

        for skill in skills:
            lines.append(f"### {skill.name}")
            lines.append(f"{skill.description}\n")

            # Include skill content (truncated if too long)
            content = skill.get_content()
            # Remove frontmatter for display
            import re
            content = re.sub(r'^---\s*\n.*?\n---\s*\n', '', content, flags=re.DOTALL)

            # Replace common skill path placeholders with actual path
            actual_path = str(skill.path)
            content = content.replace(f"~/.claude/skills/{skill.name}/", f"{actual_path}/")
            content = content.replace(f"~/.claude/skills/{skill.name}", actual_path)

            if len(content) > 2000:
                content = content[:2000] + "\n...(truncated)"

            lines.append(content)
            lines.append("")

        return "\n".join(lines)
