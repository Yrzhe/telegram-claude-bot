"""Constraint Extractor - Extract user corrections and constraints from chat history"""

import re
import logging
from typing import Optional
from pathlib import Path

logger = logging.getLogger(__name__)

# Patterns that indicate user is correcting/constraining
CORRECTION_PATTERNS = [
    # Chinese patterns
    r"不要[^。，\n]{2,50}",  # "不要..." - don't do X
    r"别[^。，\n]{2,50}",  # "别..." - don't
    r"不是[^。，\n]{2,50}",  # "不是..." - not this
    r"你怎么又[^。，\n]{2,50}",  # "你怎么又..." - why did you again
    r"我说的是[^。，\n]{2,50}",  # "我说的是..." - what I said was
    r"都说了[^。，\n]{2,50}",  # "都说了..." - I already said
    r"我讲的是[^。，\n]{2,50}",  # "我讲的是..." - what I'm talking about is
    r"不是这个[^。，\n]{0,30}",  # "不是这个" - not this one
    r"又忘了[^。，\n]{0,30}",  # "又忘了" - forgot again
    r"不对[^。，\n]{0,30}",  # "不对" - wrong
    r"错了[^。，\n]{0,30}",  # "错了" - wrong
    r"不用[^。，\n]{2,30}",  # "不用..." - no need to
    r"只[要需是讲说][^。，\n]{2,50}",  # "只要/只需/只是..." - only want/need

    # English patterns
    r"don't [^.\n]{2,50}",
    r"not [^.\n]{2,50}",
    r"I said [^.\n]{2,50}",
    r"I meant [^.\n]{2,50}",
    r"you forgot [^.\n]{2,50}",
    r"wrong[^.\n]{0,30}",
    r"no need to [^.\n]{2,50}",
    r"only [^.\n]{2,50}",
]

# Compile patterns for efficiency
COMPILED_PATTERNS = [re.compile(p, re.IGNORECASE) for p in CORRECTION_PATTERNS]


def extract_constraints_from_message(message: str) -> list[str]:
    """
    Extract constraint phrases from a single message.

    Args:
        message: User message text

    Returns:
        List of constraint phrases found
    """
    constraints = []

    for pattern in COMPILED_PATTERNS:
        matches = pattern.findall(message)
        for match in matches:
            # Clean up the match
            constraint = match.strip()
            if len(constraint) > 5:  # Filter out too short matches
                constraints.append(constraint)

    return constraints


def extract_constraints_from_chat_log(
    chat_log: str,
    max_messages: int = 10
) -> list[str]:
    """
    Extract constraints from recent chat log.

    Args:
        chat_log: Full chat log text
        max_messages: Maximum number of recent messages to scan

    Returns:
        List of unique constraints found
    """
    if not chat_log:
        return []

    constraints = []
    seen = set()

    # Split by message separator and get recent user messages
    sections = chat_log.split("=" * 60)
    recent_sections = sections[-max_messages:] if len(sections) > max_messages else sections

    for section in recent_sections:
        # Only look at user messages
        if "👤 User:" in section:
            # Extract user message content
            try:
                user_part = section.split("👤 User:")[1]
                # Remove agent response if present
                if "🤖 Agent:" in user_part:
                    user_part = user_part.split("🤖 Agent:")[0]

                user_message = user_part.strip()

                # Extract constraints from this message
                msg_constraints = extract_constraints_from_message(user_message)
                for c in msg_constraints:
                    c_lower = c.lower()
                    if c_lower not in seen:
                        seen.add(c_lower)
                        constraints.append(c)

            except (IndexError, ValueError):
                continue

    return constraints


def format_constraints_for_prompt(constraints: list[str]) -> str:
    """
    Format constraints as a prompt prefix.

    Args:
        constraints: List of constraint phrases

    Returns:
        Formatted constraint reminder string
    """
    if not constraints:
        return ""

    # Deduplicate and limit
    unique_constraints = list(dict.fromkeys(constraints))[:8]  # Max 8 constraints

    lines = ["[⚠️ ACTIVE CONSTRAINTS - You MUST follow these:]"]
    for i, c in enumerate(unique_constraints, 1):
        lines.append(f"{i}. {c}")
    lines.append("[Your response MUST NOT violate any of the above constraints.]\n")

    return "\n".join(lines)


def get_constraints_prefix(
    chat_log: Optional[str],
    max_messages: int = 10
) -> str:
    """
    Main function: Get constraint prefix to prepend to user message.

    Args:
        chat_log: Chat log text (or None)
        max_messages: Number of recent messages to scan

    Returns:
        Constraint prefix string (empty if no constraints found)
    """
    if not chat_log:
        return ""

    try:
        constraints = extract_constraints_from_chat_log(chat_log, max_messages)
        if constraints:
            prefix = format_constraints_for_prompt(constraints)
            logger.info(f"Extracted {len(constraints)} constraints from chat history")
            return prefix
        return ""
    except Exception as e:
        logger.error(f"Failed to extract constraints: {e}")
        return ""
