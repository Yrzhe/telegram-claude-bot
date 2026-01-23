"""Bash Safety Checker - Multi-layer security for Bash command execution"""

import re
import logging
from pathlib import Path
from typing import Tuple, Optional
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)


class SafetyLevel(Enum):
    """Safety classification levels"""
    SAFE = "safe"           # Whitelisted, always allow
    MODERATE = "moderate"   # Needs path check, generally safe
    DANGEROUS = "dangerous" # Blacklisted, always deny
    UNKNOWN = "unknown"     # Needs LLM review


@dataclass
class SafetyCheckResult:
    """Result of a safety check"""
    is_safe: bool
    level: SafetyLevel
    reason: str
    command: str


# Dangerous command patterns - ALWAYS DENY
DANGEROUS_PATTERNS = [
    # System destruction
    r'rm\s+(-[rf]+\s+)*(/|~|\*|/\*)',  # rm -rf /, rm -rf ~, etc.
    r'rm\s+-[rf]*\s+\.\.',             # rm -rf ..
    r':()\s*{\s*:\|\:&\s*}\s*;:',      # Fork bomb
    r'mkfs\.',                          # Format filesystem
    r'dd\s+if=/dev/(zero|random|urandom)\s+of=/',  # Overwrite disk

    # System control
    r'\bsudo\b',                        # Sudo commands
    r'\bsu\s+-',                        # Switch user
    r'\bshutdown\b',
    r'\breboot\b',
    r'\binit\s+[0-6]',
    r'\bsystemctl\s+(stop|disable|mask)',
    r'\bkillall\b',
    r'\bpkill\s+-9',

    # Permission attacks
    r'chmod\s+(-R\s+)?[0-7]*77[0-7]*\s+/',  # chmod 777 /
    r'chown\s+-R\s+.*\s+/',                  # chown -R on root

    # Network attacks
    r'nc\s+-[el]',                      # Netcat listen/execute
    r'nmap\b',                          # Port scanning
    r'/dev/tcp/',                       # Bash TCP

    # Sensitive file access
    r'cat\s+.*/etc/(passwd|shadow|sudoers)',
    r'>\s*/etc/',                       # Writing to /etc
    r'/proc/|/sys/',                    # System directories

    # Code injection
    r'\beval\s+',                       # Eval command
    r'\$\([^)]*\)',                     # Command substitution (needs review)
    r'`[^`]+`',                         # Backtick substitution

    # Environment manipulation
    r'export\s+PATH=',                  # PATH manipulation
    r'export\s+LD_',                    # Library path manipulation
    r'\.bashrc|\.bash_profile|\.profile',  # Shell config files

    # History and logs
    r'history\s+-[cd]',                 # Delete history
    r'>\s*/var/log/',                   # Clear logs

    # Dangerous wget/curl
    r'(wget|curl)\s+.*\|\s*(ba)?sh',   # Pipe to shell
    r'(wget|curl)\s+.*-O\s*/bin/',     # Download to bin
]

# Safe command prefixes - ALWAYS ALLOW (within working directory)
SAFE_PREFIXES = [
    'python', 'python3',
    'pip', 'pip3',
    'ls', 'pwd', 'echo',
    'cat', 'head', 'tail', 'less', 'more',
    'wc', 'sort', 'uniq', 'grep', 'awk', 'sed',
    'mkdir', 'touch',
    'cp', 'mv',  # Will be path-checked
    'find', 'locate',
    'git',
    'node', 'npm', 'npx',
    'which', 'whereis', 'type',
    'date', 'cal',
    'file', 'stat',
    'diff', 'cmp',
    'tar', 'zip', 'unzip', 'gzip', 'gunzip',
    'ffmpeg', 'convert', 'identify',  # Image/video processing
    'jq', 'yq',  # JSON/YAML processing
]

# Commands that need path validation
PATH_SENSITIVE_COMMANDS = [
    'rm', 'rmdir',
    'cp', 'mv',
    'chmod', 'chown',
    'ln',
]


def _normalize_command(command: str) -> str:
    """Normalize command for analysis."""
    # Remove leading/trailing whitespace
    cmd = command.strip()
    # Remove comments
    cmd = re.sub(r'#.*$', '', cmd, flags=re.MULTILINE)
    # Normalize whitespace
    cmd = ' '.join(cmd.split())
    return cmd


def _check_dangerous_patterns(command: str) -> Optional[str]:
    """Check if command matches any dangerous patterns."""
    for pattern in DANGEROUS_PATTERNS:
        if re.search(pattern, command, re.IGNORECASE):
            return f"Command matches dangerous pattern: {pattern}"
    return None


def _get_command_prefix(command: str) -> str:
    """Extract the main command (first word)."""
    # Handle cd && command, or command ; command
    parts = re.split(r'[;&|]', command)
    if parts:
        first_cmd = parts[0].strip()
        # Handle 'cd /path && python script.py'
        if first_cmd.startswith('cd '):
            if len(parts) > 1:
                first_cmd = parts[1].strip()
        words = first_cmd.split()
        if words:
            return words[0]
    return ""


def _is_safe_prefix(command: str) -> bool:
    """Check if command starts with a safe prefix."""
    prefix = _get_command_prefix(command)
    return prefix in SAFE_PREFIXES


def _extract_paths(command: str) -> list[str]:
    """Extract file paths from a command."""
    paths = []
    # Match quoted paths
    quoted = re.findall(r'["\']([^"\']+)["\']', command)
    paths.extend(quoted)
    # Match unquoted paths (starting with / or . or ~)
    unquoted = re.findall(r'(?:^|\s)((?:/|\.{1,2}/|~)[^\s;|&]+)', command)
    paths.extend(unquoted)
    return paths


def _is_path_within_working_dir(path: str, working_dir: Path) -> bool:
    """Check if a path is within the working directory."""
    try:
        # Expand ~ to home directory
        if path.startswith('~'):
            return False  # Don't allow home directory access

        # Handle relative paths
        if not path.startswith('/'):
            full_path = (working_dir / path).resolve()
        else:
            full_path = Path(path).resolve()

        # Check if within working directory
        full_path.relative_to(working_dir.resolve())
        return True
    except (ValueError, OSError):
        return False


def check_bash_safety(
    command: str,
    working_dir: Path,
    user_id: int
) -> SafetyCheckResult:
    """
    Check if a Bash command is safe to execute.

    Args:
        command: The Bash command to check
        working_dir: User's working directory
        user_id: User ID for logging

    Returns:
        SafetyCheckResult with safety assessment
    """
    normalized = _normalize_command(command)

    if not normalized:
        return SafetyCheckResult(
            is_safe=False,
            level=SafetyLevel.DANGEROUS,
            reason="Empty command",
            command=command
        )

    # Layer 1: Check dangerous patterns
    danger_reason = _check_dangerous_patterns(normalized)
    if danger_reason:
        logger.warning(f"User {user_id} Bash BLOCKED (dangerous): {command[:100]}")
        return SafetyCheckResult(
            is_safe=False,
            level=SafetyLevel.DANGEROUS,
            reason=danger_reason,
            command=command
        )

    # Layer 2: Check if command starts with safe prefix
    prefix = _get_command_prefix(normalized)

    # Layer 3: Path-sensitive commands need path validation
    if prefix in PATH_SENSITIVE_COMMANDS:
        paths = _extract_paths(normalized)
        for path in paths:
            if not _is_path_within_working_dir(path, working_dir):
                logger.warning(f"User {user_id} Bash BLOCKED (path): {command[:100]} - path: {path}")
                return SafetyCheckResult(
                    is_safe=False,
                    level=SafetyLevel.DANGEROUS,
                    reason=f"Path '{path}' is outside your working directory",
                    command=command
                )

        # Paths are OK, allow
        logger.info(f"User {user_id} Bash ALLOWED (path-checked): {command[:100]}")
        return SafetyCheckResult(
            is_safe=True,
            level=SafetyLevel.MODERATE,
            reason="Path-sensitive command with valid paths",
            command=command
        )

    # Layer 4: Safe prefixes are always allowed
    if _is_safe_prefix(normalized):
        logger.info(f"User {user_id} Bash ALLOWED (safe prefix): {command[:100]}")
        return SafetyCheckResult(
            is_safe=True,
            level=SafetyLevel.SAFE,
            reason="Command uses safe prefix",
            command=command
        )

    # Layer 5: Unknown commands - allow but log
    # In a stricter mode, we could deny or require LLM review here
    logger.info(f"User {user_id} Bash ALLOWED (unknown, monitored): {command[:100]}")
    return SafetyCheckResult(
        is_safe=True,
        level=SafetyLevel.UNKNOWN,
        reason="Command not in whitelist but no dangerous patterns detected",
        command=command
    )


# Additional validation for specific dangerous operations
def validate_rm_command(command: str, working_dir: Path) -> Tuple[bool, str]:
    """Special validation for rm commands."""
    # Don't allow rm with -rf and wildcard or parent
    if re.search(r'rm\s+.*-[rf]*.*(\*|\.\.)', command):
        return False, "rm with wildcards or parent directory is not allowed"

    # Check all paths in rm command
    paths = _extract_paths(command)
    for path in paths:
        if not _is_path_within_working_dir(path, working_dir):
            return False, f"Cannot delete files outside working directory: {path}"

    return True, "OK"
