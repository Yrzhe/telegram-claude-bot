"""Prompt Builder - Modular system prompt assembly"""

import logging
from pathlib import Path
from typing import Optional
from datetime import datetime
import yaml
import re

logger = logging.getLogger(__name__)

# Weekday names
WEEKDAY_NAMES = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']

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
    additional_sections: Optional[dict[str, str]] = None,
    topic_context: Optional[str] = None,
    user_data_dir: Optional[str] = None
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
        topic_context: Topic context string from TopicManager
        user_data_dir: User's data directory for loading memories

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

        # Build user memories string
        memories_str = ""
        if user_data_dir:
            try:
                from .memory import MemoryManager
                from pathlib import Path
                manager = MemoryManager(Path(user_data_dir))
                memories = manager.search_memories(active_only=True, limit=20)
                if memories:
                    memories_str = "Use this information to personalize your responses:\n\n"
                    # Group by category
                    by_category = {}
                    for m in memories:
                        cat = m.category
                        if cat not in by_category:
                            by_category[cat] = []
                        by_category[cat].append(m)

                    for cat, mems in by_category.items():
                        memories_str += f"**{cat.title()}**:\n"
                        for m in mems[:5]:  # Max 5 per category
                            memories_str += f"- {m.content}\n"
                        memories_str += "\n"
                else:
                    memories_str = "(No memories saved yet - learn about this user through conversation)"
            except Exception as e:
                logger.debug(f"Failed to load user memories: {e}")
                memories_str = "(Memory system unavailable)"
        else:
            memories_str = "(Memory system not configured)"

        # Get current date info
        now = datetime.now()
        current_date = now.strftime('%Y-%m-%d')
        current_weekday = WEEKDAY_NAMES[now.weekday()]

        # Replace placeholders
        context = context.replace("{current_date}", current_date)
        context = context.replace("{current_weekday}", current_weekday)
        context = context.replace("{user_id}", str(user_id))
        context = context.replace("{user_display_name}", user_display_name or "Unknown")
        context = context.replace("{working_directory}", working_directory)
        context = context.replace("{storage_info}", storage_str)
        context = context.replace("{user_memories}", memories_str)
        context = context.replace("{context_summary}", context_str)

        sections.append(context)

    # 2.5. Topic Context (Dynamic topic information)
    if topic_context:
        sections.append(topic_context)

    # 3. Rules (Operational guidelines)
    rules = load_prompt_module("rules")
    if rules:
        sections.append(rules)

    # 4. Task Understanding (How to parse complex user requests)
    task_understanding = load_prompt_module("task_understanding")
    if task_understanding:
        sections.append(task_understanding)

    # 5. Memory (Proactive learning and recall)
    memory = load_prompt_module("memory")
    if memory:
        sections.append(memory)

    # 6. Tools (Available capabilities)
    tools = load_prompt_module("tools")
    if tools:
        sections.append(tools)

    # 7. Skills (Dynamically loaded)
    skills_intro = load_prompt_module("skills_intro")
    if skills_intro:
        # Get available skills and format them
        available_skills = get_available_skills()
        skills_list = format_skills_list(available_skills)
        skills_intro = skills_intro.replace("{skills_list}", skills_list)
        sections.append(skills_intro)

    # 8. Additional sections (if any)
    if additional_sections:
        for section_name, content in additional_sections.items():
            sections.append(f"# {section_name}\n\n{content}")

    # 9. Custom user skills (if any)
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


def build_sub_agent_prompt(
    task_description: str,
    working_directory: str,
    review_criteria: Optional[str] = None,
    retry_history: Optional[list] = None,
    custom_skills_content: Optional[str] = None
) -> str:
    """
    Build system prompt for Sub Agent using modular components.

    Args:
        task_description: Description of the delegated task
        working_directory: User's working directory path
        review_criteria: Quality criteria for review (if any)
        retry_history: List of previous retry attempts with feedback
        custom_skills_content: User's custom skills content

    Returns:
        Complete system prompt for Sub Agent
    """
    sections = []

    # 1. Sub Agent Identity
    now = datetime.now()
    current_date = now.strftime('%Y-%m-%d')
    current_weekday = WEEKDAY_NAMES[now.weekday()]

    identity = f"""# Sub Agent Identity

You are a Sub Agent working on a delegated task. You work independently and report results back to the Main Agent.

## Current Time

- **Today's Date**: {current_date}
- **Day of Week**: {current_weekday}

**CRITICAL**: For time-sensitive data (stock prices, news, financial reports), ALWAYS verify the data timestamp. Never report stale data as current.

## Your Task

{task_description}"""

    if review_criteria:
        identity += f"""

## Quality Criteria

Your output will be reviewed against these criteria:
{review_criteria}"""

    sections.append(identity)

    # 2. Retry History (if any) - Enhanced with suggestions and missing dimensions
    if retry_history and len(retry_history) > 0:
        history_section = """# Previous Attempts

**IMPORTANT**: Learn from these previous failures. Do NOT repeat the same mistakes! Each rejection includes specific improvement directions - follow them carefully.

"""
        for i, entry in enumerate(retry_history, 1):
            feedback = entry.get('feedback', 'No feedback')
            timestamp = entry.get('timestamp', 'N/A')
            suggestions = entry.get('suggestions', [])
            missing_dimensions = entry.get('missing_dimensions', [])
            result_summary = entry.get('result_summary', '')

            history_section += f"""## Attempt {i}
**Time**: {timestamp}
**Rejection Reason**: {feedback}
"""
            if missing_dimensions:
                history_section += f"""
**Missing Dimensions**:
{chr(10).join('- ' + d for d in missing_dimensions)}
"""
            if suggestions:
                history_section += f"""
**Main Agent's Suggested Directions**:
{chr(10).join('- ' + s for s in suggestions)}
"""
            if result_summary:
                history_section += f"""
**Previous Result Summary**: {result_summary[:300]}...
"""
            history_section += """
---
"""
        sections.append(history_section)

    # 3. Skills (Dynamically loaded - same as main agent)
    skills_intro = load_prompt_module("skills_intro")
    if skills_intro:
        available_skills = get_available_skills()
        skills_list = format_skills_list(available_skills)
        skills_intro = skills_intro.replace("{skills_list}", skills_list)
        sections.append(skills_intro)

    # 4. Sub Agent Rules
    rules = """# Sub Agent Rules

## Core Principle: Deep Exploration

As a Sub Agent, you must adopt an explorer's mindset:
1. **Don't stay shallow** - Don't just list data, analyze "why"
2. **Dig into anomalies** - Unusual points are often the most valuable
3. **Data must be reliable** - Clear sources, cross-verify important data
4. **Learn from rejections** - If there are previous attempts, address all issues

## File Operations

- You can ONLY create/write files in these directories: reports/, analysis/, documents/, output/, temp/
- Use temp/ for intermediate files that don't need to be sent
- NEVER use /tmp, /var, or any system directory
- Always use relative paths like "reports/my_report.txt", NOT absolute paths
- NEVER show full system paths like /app/users/xxx - use relative paths only

## Output Rules

1. Save report files to appropriate directories (reports/, analysis/, documents/, output/)
2. You CANNOT send messages or files to users directly - you are a background worker
3. After completing, return a comprehensive result summary - the Main Agent will handle user communication
4. For time-sensitive data, ALWAYS include the data date/timestamp in your report

## Data Verification Rules

For any research task:
1. Use Skills (akshare-stocks, akshare-a-shares, web-research) to get accurate data
2. **MUST cite data sources and retrieval time**
3. Cross-verify important data from multiple sources
4. If data conflicts found, analyze reasons and state clearly
5. Historical data must be clearly dated

## Research Depth Requirements

1. **Foundation level**: Collect relevant data and facts
2. **Analysis level**: Analyze reasons and trends behind the data
3. **Insight level**: Provide unique insights, discover unusual points
4. **Recommendation level**: Give actionable suggestions

Each research dimension should aim for the insight level, not stay at the foundation level.

## Handling Rejections

If you see "Previous Attempts":
1. Carefully read the rejection reason from each attempt
2. Pay special attention to "Missing Dimensions" and "Suggested Directions"
3. This submission must address ALL previous issues
4. Explore deeply in the new directions"""

    sections.append(rules)

    # 5. Custom user skills (if any)
    if custom_skills_content:
        sections.append(f"# User Custom Skills\n\n{custom_skills_content}")

    return "\n\n---\n\n".join(sections)
