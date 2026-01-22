"""Skill Validator - Security and format validation for user-uploaded skills"""

import re
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Tuple

logger = logging.getLogger(__name__)


@dataclass
class SkillValidationResult:
    """Result of skill validation"""
    is_valid: bool
    skill_name: Optional[str] = None
    skill_description: Optional[str] = None
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    def add_error(self, msg: str):
        self.errors.append(msg)
        self.is_valid = False

    def add_warning(self, msg: str):
        self.warnings.append(msg)


class SkillValidator:
    """
    Validates user-uploaded skills for:
    1. Format compliance (SKILL.md with proper frontmatter)
    2. Security (no malicious code patterns)
    3. Prompt injection protection
    """

    # Dangerous patterns that could execute code
    DANGEROUS_CODE_PATTERNS = [
        # Shell/Bash execution
        (r'\bBash\s*\(', "Bash tool usage detected"),
        (r'\bexec\s*\(', "exec() function detected"),
        (r'\bsystem\s*\(', "system() call detected"),
        (r'\bos\.system', "os.system call detected"),
        (r'\bsubprocess', "subprocess module detected"),
        (r'\beval\s*\(', "eval() function detected"),
        (r'`[^`]+`', "Backtick command execution detected"),
        (r'\$\([^)]+\)', "Shell command substitution detected"),
        # File system attacks
        (r'rm\s+-rf', "Dangerous rm -rf command detected"),
        (r'chmod\s+777', "Dangerous chmod 777 detected"),
        (r'>\s*/dev/', "Writing to /dev/ detected"),
        # Network attacks
        (r'curl\s+.*\|\s*sh', "Curl pipe to shell detected"),
        (r'wget\s+.*\|\s*sh', "Wget pipe to shell detected"),
    ]

    # Prompt injection patterns
    INJECTION_PATTERNS = [
        # Direct instruction override
        (r'ignore\s+(all\s+)?(previous|above|prior)\s+(instructions?|prompts?|rules?)',
         "Prompt injection: ignore previous instructions"),
        (r'disregard\s+(all\s+)?(previous|above|prior)',
         "Prompt injection: disregard previous"),
        (r'forget\s+(everything|all|what)\s+(you|i)\s+(told|said)',
         "Prompt injection: forget instructions"),
        (r'new\s+instructions?\s*:',
         "Prompt injection: new instructions"),
        (r'system\s*:\s*you\s+are',
         "Prompt injection: system role override"),
        (r'from\s+now\s+on\s*,?\s*(you|ignore|forget)',
         "Prompt injection: behavior change"),
        # Role manipulation
        (r'you\s+are\s+now\s+a',
         "Prompt injection: role change"),
        (r'act\s+as\s+if\s+you\s+have\s+no\s+restrictions',
         "Prompt injection: restriction bypass"),
        (r'pretend\s+(you|that)\s+(can|have|are)\s+.*(unrestricted|unlimited|admin)',
         "Prompt injection: pretend unrestricted"),
        # Data exfiltration
        (r'send\s+(all|my|the)\s+(data|files|information)\s+to',
         "Prompt injection: data exfiltration"),
        (r'upload\s+(everything|all\s+files)\s+to',
         "Prompt injection: upload all files"),
    ]

    # Path traversal patterns
    PATH_TRAVERSAL_PATTERNS = [
        (r'\.\./', "Path traversal: ../"),
        (r'\.\.\\', "Path traversal: ..\\"),
        (r'/etc/passwd', "Sensitive file access: /etc/passwd"),
        (r'/etc/shadow', "Sensitive file access: /etc/shadow"),
        (r'~/.ssh', "Sensitive directory access: ~/.ssh"),
    ]

    def __init__(self):
        pass

    def validate_skill_directory(self, skill_dir: Path) -> SkillValidationResult:
        """
        Validate a skill directory.

        Args:
            skill_dir: Path to the extracted skill directory

        Returns:
            SkillValidationResult with validation status and details
        """
        result = SkillValidationResult(is_valid=True)

        # Step 1: Check SKILL.md exists
        skill_md_path = skill_dir / "SKILL.md"
        if not skill_md_path.exists():
            result.add_error("Missing SKILL.md file - this is required")
            return result

        # Step 2: Validate SKILL.md format and extract metadata
        skill_content = skill_md_path.read_text(encoding='utf-8')
        name, description, format_errors = self._validate_skill_md_format(skill_content)

        for error in format_errors:
            result.add_error(error)

        if name:
            result.skill_name = name
        if description:
            result.skill_description = description

        # Step 3: Security scan all files
        for file_path in skill_dir.rglob('*'):
            if file_path.is_file():
                self._scan_file_security(file_path, result)

        return result

    def _validate_skill_md_format(self, content: str) -> Tuple[Optional[str], Optional[str], List[str]]:
        """
        Validate SKILL.md format and extract name/description.

        Returns:
            (name, description, errors)
        """
        errors = []
        name = None
        description = None

        # Check for YAML frontmatter
        frontmatter_pattern = r'^---\s*\n(.*?)\n---'
        match = re.match(frontmatter_pattern, content, re.DOTALL)

        if not match:
            errors.append("Missing YAML frontmatter (must start with --- and end with ---)")
            return name, description, errors

        frontmatter = match.group(1)

        # Extract name
        name_match = re.search(r'^name:\s*(.+)$', frontmatter, re.MULTILINE)
        if name_match:
            name = name_match.group(1).strip()
            # Validate name format
            if not re.match(r'^[a-zA-Z0-9_-]+$', name):
                errors.append(f"Invalid skill name '{name}' - use only letters, numbers, underscore, hyphen")
        else:
            errors.append("Missing 'name' field in frontmatter")

        # Extract description
        desc_match = re.search(r'^description:\s*(.+)$', frontmatter, re.MULTILINE)
        if desc_match:
            description = desc_match.group(1).strip()
        else:
            errors.append("Missing 'description' field in frontmatter")

        # Check for required sections in content
        body = content[match.end():]

        if '## ' not in body and '# ' not in body:
            errors.append("SKILL.md should have section headers (## Usage, ## Steps, etc.)")

        return name, description, errors

    def _scan_file_security(self, file_path: Path, result: SkillValidationResult):
        """Scan a file for security issues."""

        # Only scan text files
        try:
            content = file_path.read_text(encoding='utf-8')
        except (UnicodeDecodeError, PermissionError):
            # Binary file or unreadable, skip
            return

        relative_path = file_path.name

        # Check dangerous code patterns
        for pattern, message in self.DANGEROUS_CODE_PATTERNS:
            if re.search(pattern, content, re.IGNORECASE):
                result.add_error(f"[{relative_path}] {message}")

        # Check prompt injection patterns
        for pattern, message in self.INJECTION_PATTERNS:
            if re.search(pattern, content, re.IGNORECASE):
                result.add_error(f"[{relative_path}] {message}")

        # Check path traversal
        for pattern, message in self.PATH_TRAVERSAL_PATTERNS:
            if re.search(pattern, content):
                result.add_error(f"[{relative_path}] {message}")

        # Check file size (warn if too large)
        file_size = file_path.stat().st_size
        if file_size > 100 * 1024:  # 100KB
            result.add_warning(f"[{relative_path}] Large file ({file_size // 1024}KB)")

    def suggest_fixes(self, result: SkillValidationResult) -> List[str]:
        """Generate fix suggestions based on validation errors."""
        suggestions = []

        for error in result.errors:
            if "Missing SKILL.md" in error:
                suggestions.append(
                    "Create a SKILL.md file with this format:\n"
                    "---\n"
                    "name: your-skill-name\n"
                    "description: What this skill does\n"
                    "---\n\n"
                    "# Skill Title\n\n"
                    "## Usage\n- When to use this skill\n\n"
                    "## Steps\n1. Step one\n2. Step two"
                )
            elif "Missing YAML frontmatter" in error:
                suggestions.append(
                    "Add YAML frontmatter at the start of SKILL.md:\n"
                    "---\n"
                    "name: skill-name\n"
                    "description: description here\n"
                    "---"
                )
            elif "Missing 'name'" in error:
                suggestions.append("Add 'name: your-skill-name' to the frontmatter")
            elif "Missing 'description'" in error:
                suggestions.append("Add 'description: what it does' to the frontmatter")
            elif "Prompt injection" in error:
                suggestions.append(
                    "Remove phrases that try to override instructions. "
                    "Skills should provide helpful guidance, not manipulate the AI."
                )
            elif "Bash" in error or "exec" in error or "system" in error:
                suggestions.append(
                    "Remove code execution commands. Skills should guide the Agent, "
                    "not execute arbitrary code."
                )

        return suggestions
