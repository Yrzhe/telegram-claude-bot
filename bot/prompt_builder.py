"""Prompt Builder - Modular system prompt assembly"""

import logging
from pathlib import Path
from typing import Optional
import yaml
import re

logger = logging.getLogger(__name__)

# Base directory for prompt modules
PROMPTS_DIR = Path(__file__).parent.parent / "prompts"
SKILLS_DIR = Path(__file__).parent.parent / ".claude" / "skills"


def load_prompt_module(name: str) -> str:
    """Load a prompt module file by name."""
    file_path = PROMPTS_DIR / f"{name}.md"
    try:
        return file_path.read_text(encoding='utf-8')
    except FileNotFoundError:
        logger.warning(f"Prompt module not found: {file_path}")
        return ""


def extract_skill_metadata(skill_dir: Path) -> Optional[dict]:
    """Extract metadata from a skill's SKILL.md file."""
    skill_file = skill_dir / "SKILL.md"
    if not skill_file.exists():
        return None

    try:
        content = skill_file.read_text(encoding='utf-8')

        # Extract YAML frontmatter
        if content.startswith('---'):
            parts = content.split('---', 2)
            if len(parts) >= 3:
                frontmatter = parts[1].strip()
                try:
                    metadata = yaml.safe_load(frontmatter)
                    if metadata:
                        metadata['skill_name'] = skill_dir.name
                        return metadata
                except yaml.YAMLError:
                    pass

        # Fallback: extract from content
        name = skill_dir.name
        description = ""

        # Try to find description in first paragraph
        lines = content.split('\n')
        for line in lines:
            if line.strip() and not line.startswith('#') and not line.startswith('-'):
                description = line.strip()[:100]
                break

        return {
            'skill_name': name,
            'name': name,
            'description': description or f"Skill: {name}"
        }

    except Exception as e:
        logger.error(f"Error reading skill metadata from {skill_file}: {e}")
        return None


def get_available_skills() -> list[dict]:
    """Get list of available skills with their metadata."""
    skills = []

    if not SKILLS_DIR.exists():
        return skills

    for skill_dir in SKILLS_DIR.iterdir():
        if skill_dir.is_dir() and not skill_dir.name.startswith('.'):
            metadata = extract_skill_metadata(skill_dir)
            if metadata:
                skills.append(metadata)

    # Sort by name
    skills.sort(key=lambda x: x.get('name', x.get('skill_name', '')))
    return skills


def format_skills_list(skills: list[dict]) -> str:
    """Format skills list for inclusion in system prompt."""
    if not skills:
        return "No skills currently available."

    lines = []
    for skill in skills:
        name = skill.get('name', skill.get('skill_name', 'unknown'))
        description = skill.get('description', '')
        triggers = skill.get('triggers', [])

        # Format: - skill-name: description
        line = f"- **{name}**: {description}"

        # Add triggers if available
        if triggers and isinstance(triggers, list):
            trigger_str = ", ".join(triggers[:3])  # Max 3 triggers
            line += f" (use when: {trigger_str})"

        lines.append(line)

    return "\n".join(lines)


def build_system_prompt(
    user_id: int,
    user_display_name: str,
    working_directory: str,
    storage_info: Optional[dict] = None,
    context_summary: Optional[str] = None,
    custom_skills_content: Optional[str] = None,
    additional_sections: Optional[dict[str, str]] = None
) -> str:
    """
    Build the complete system prompt from modular components.

    Args:
        user_id: User's Telegram ID
        user_display_name: User's display name
        working_directory: User's working directory path
        storage_info: Storage quota information
        context_summary: Previous conversation summary (from /compact)
        custom_skills_content: User's custom skills content
        additional_sections: Additional sections to add (key=section_name, value=content)

    Returns:
        Complete system prompt string
    """
    sections = []

    # 1. Soul (Identity and Personality)
    soul = load_prompt_module("soul")
    if soul:
        sections.append(soul)

    # 2. Context (Dynamic user information)
    context = load_prompt_module("context")
    if context:
        # Build storage info string
        storage_str = ""
        if storage_info:
            storage_str = f"""- Used: {storage_info.get('used_formatted', 'N/A')}
- Quota: {storage_info.get('quota_formatted', 'N/A')}
- Available: {storage_info.get('available_formatted', 'N/A')}
- Usage: {storage_info.get('percentage', 0)}%"""

        # Build context summary string
        context_str = ""
        if context_summary:
            context_str = f"""
Previous Conversation Summary (IMPORTANT - Read this to understand context):
---
{context_summary}
---
This summary contains key information from our previous conversation that was compacted to save context space.
Use this information to maintain continuity with the user."""

        # Replace placeholders
        context = context.replace("{user_id}", str(user_id))
        context = context.replace("{user_display_name}", user_display_name or "Unknown")
        context = context.replace("{working_directory}", working_directory)
        context = context.replace("{storage_info}", storage_str)
        context = context.replace("{context_summary}", context_str)

        sections.append(context)

    # 3. Rules (Operational guidelines)
    rules = load_prompt_module("rules")
    if rules:
        sections.append(rules)

    # 4. Tools (Available capabilities)
    tools = load_prompt_module("tools")
    if tools:
        sections.append(tools)

    # 5. Skills (Dynamically loaded)
    skills_intro = load_prompt_module("skills_intro")
    if skills_intro:
        # Get available skills and format them
        available_skills = get_available_skills()
        skills_list = format_skills_list(available_skills)
        skills_intro = skills_intro.replace("{skills_list}", skills_list)
        sections.append(skills_intro)

    # 6. Additional sections (if any)
    if additional_sections:
        for section_name, content in additional_sections.items():
            sections.append(f"# {section_name}\n\n{content}")

    # 7. Custom user skills (if any)
    if custom_skills_content:
        sections.append(f"# User Custom Skills\n\n{custom_skills_content}")

    # Assemble the complete prompt
    return "\n\n---\n\n".join(sections)


def get_fallback_prompt(user_id: int, working_directory: str) -> str:
    """Get a minimal fallback prompt if module loading fails."""
    return f"""You are an AI assistant in a Telegram bot.
User ID: {user_id}
Working directory: {working_directory}

Respond helpfully in the user's language."""
