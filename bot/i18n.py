"""Internationalization (i18n) module for Telegram Bot

This module centralizes all user-facing strings for easy translation.
Currently supports English as the default language.

To add a new language:
1. Create a new class (e.g., StringsZH) with the same structure as Strings
2. Update get_strings() to return the appropriate class based on language setting
"""

from dataclasses import dataclass
from typing import Dict


@dataclass
class Strings:
    """English strings (default)"""

    # ===== General =====
    NO_PERMISSION: str = "You don't have permission to use this bot"
    OPERATION_FAILED: str = "Operation failed"
    PARAMETER_ERROR: str = "Invalid parameter format"
    UNKNOWN_COMMAND: str = "Unknown command, use /admin for help"

    # ===== Start/Help =====
    WELCOME_TITLE: str = "Welcome to File Management Bot!"
    STORAGE_LABEL: str = "Your storage:"
    USED_LABEL: str = "Used"
    SESSION_INFO: str = "Current session: {message_count} messages sent, {remaining_minutes} min remaining"
    SESSION_INFO_PERSISTENT: str = "Current session: {message_count} messages sent (persistent)"
    AI_MODE_DESC: str = "AI Mode: Send any message to chat with Claude assistant (with context memory)"

    COMMAND_LIST_TITLE: str = "Commands:"
    CMD_LS: str = "/ls [path] - List directory contents"
    CMD_STORAGE: str = "/storage - View storage usage"
    CMD_SESSION: str = "/session - View current session status"
    CMD_NEW: str = "/new - Start new session (clear context)"
    CMD_ENV: str = "/env - Manage environment variables"
    CMD_PACKAGES: str = "/packages - Manage Python packages"
    CMD_SCHEDULE: str = "/schedule - Manage scheduled tasks"
    CMD_SKILL: str = "/skill - Manage custom skills"
    CMD_HELP: str = "/help - Show help info"

    EXAMPLES_TITLE: str = "Examples:"
    EXAMPLE_CREATE_FILE: str = '- Send "Create a hello.txt file for me"'
    EXAMPLE_LIST_FILES: str = '- Send "List all files"'

    # ===== Session =====
    NO_ACTIVE_SESSION: str = "No active session\n\nSend any message to start a new session. Sessions timeout after 30 minutes."
    SESSION_STATUS_TITLE: str = "Current Session Status"
    SESSION_ID_LABEL: str = "Session ID"
    MESSAGE_COUNT_LABEL: str = "Messages"
    IDLE_TIME_LABEL: str = "Idle time"
    REMAINING_TIME_LABEL: str = "Remaining"
    SECONDS: str = "seconds"
    MINUTES: str = "minutes"
    NO_EXPIRY: str = "Never expires"
    NEW_SESSION_HINT: str = "Send /new to start a new session (clear context)"
    SESSION_CLEARED: str = "Previous session cleared, starting new conversation.\n\nSend any message to begin."
    NO_SESSION_TO_CLEAR: str = "No active session.\n\nSend any message to start a new session."

    # ===== Storage =====
    STORAGE_TITLE: str = "Storage Usage"
    QUOTA_LABEL: str = "Quota"
    AVAILABLE_LABEL: str = "Available"

    # ===== Directory Listing =====
    PATH_NOT_EXIST: str = "Path does not exist: {path}"
    NOT_A_DIRECTORY: str = "Not a directory: {path}"
    ACCESS_DENIED: str = "Access denied: path is outside allowed range"
    DIRECTORY_LABEL: str = "📂 {path}"
    EMPTY_DIRECTORY: str = "(empty)"
    ITEM_COUNT: str = "{folders} folders, {files} files"

    # ===== File Management =====
    DEL_USAGE: str = "Usage: /del <path>\n\n⚠️ Warning: Deletions cannot be undone!"
    DEL_FILE_SUCCESS: str = "🗑️ Deleted: {path} ({size})\n\n⚠️ This cannot be undone."
    DEL_FOLDER_CONFIRM: str = "⚠️ Delete folder: {path}\nContains {count} items\n\n🚨 This cannot be undone!\n\n/del confirm - Confirm delete\n/del cancel - Cancel"
    DEL_FOLDER_SUCCESS: str = "🗑️ Folder deleted: {path}\n\n⚠️ This cannot be undone."
    DEL_CANCELLED: str = "❌ Deletion cancelled"
    DEL_FAILED: str = "Failed to delete: {error}"

    # ===== Environment Variables =====
    NO_ENV_VARS: str = "No environment variables set"
    ENV_USAGE: str = "Usage:\n/env set KEY VALUE - Set\n/env del KEY - Delete"
    ENV_TITLE: str = "Environment Variables"
    ENV_SET_SUCCESS: str = "Set {key}"
    ENV_SET_FAILED: str = "Failed to set"
    ENV_DEL_SUCCESS: str = "Deleted {key}"
    ENV_DEL_FAILED: str = "Failed to delete"

    # ===== Packages =====
    PACKAGES_TITLE: str = "Python Package Management"
    PACKAGES_LIST: str = "/packages list - List installed packages"
    PACKAGES_INSTALL: str = "/packages install [name] - Install package"
    PACKAGES_INIT: str = "/packages init - Initialize virtual environment"
    CREATING_VENV: str = "Creating virtual environment..."
    VENV_SUCCESS: str = "Virtual environment created successfully!"
    VENV_FAILED: str = "Failed to create virtual environment"
    INSTALLED_PACKAGES: str = "Installed Packages"
    NO_PACKAGES: str = "No packages installed"
    GET_PACKAGES_FAILED: str = "Failed to get packages: {error}"
    INSTALLING_PACKAGE: str = "Installing {package}..."
    INSTALL_SUCCESS: str = "Installed successfully: {package}"
    INSTALL_FAILED: str = "Installation failed: {error}"
    PACKAGES_USAGE: str = "Usage: /packages [list|install package_name|init]"

    # ===== Admin =====
    NO_ADMIN_PERMISSION: str = "You don't have admin permission"
    ADMIN_HELP_TITLE: str = "Admin Commands"

    ADMIN_USER_MGMT: str = "User Management:"
    ADMIN_USERS: str = "/admin users - List all users"
    ADMIN_QUOTA: str = "/admin quota <user_id> <GB> - Set user quota"
    ADMIN_ENABLE: str = "/admin enable <user_id> - Enable user"
    ADMIN_DISABLE: str = "/admin disable <user_id> - Disable user"
    ADMIN_NOTE: str = "/admin note <user_id> <note> - Set user note"
    ADMIN_RETENTION: str = "/admin retention <user_id> <days> - Set history retention days"

    ADMIN_SESSION_MGMT: str = "Session Management:"
    ADMIN_SESSIONS: str = "/admin sessions - List active sessions"

    ADMIN_STATS_MGMT: str = "Statistics & History:"
    ADMIN_STATS: str = "/admin stats [days] - All users statistics"
    ADMIN_USERSTATS: str = "/admin userstats <user_id> [days] - Single user statistics"
    ADMIN_HISTORY: str = "/admin history <user_id> [count] - View user chat history"
    ADMIN_CLEANUP: str = "/admin cleanup - Clean up expired history"

    USER_LIST_TITLE: str = "User List"
    NO_USERS: str = "No users"
    STORAGE_LABEL_ADMIN: str = "Storage"
    RETENTION_LABEL: str = "Retention"
    DAYS: str = "days"

    ACTIVE_SESSIONS_TITLE: str = "Active Sessions"
    NO_ACTIVE_SESSIONS: str = "No active sessions"
    USER_LABEL: str = "User"
    MESSAGES_LABEL: str = "Messages"
    IDLE_LABEL: str = "Idle"

    QUOTA_SET_SUCCESS: str = "Set user {user_id} quota to {quota}GB"
    USER_ENABLED: str = "Enabled user {user_id}"
    USER_DISABLED: str = "Disabled user {user_id}"
    NOTE_SET_SUCCESS: str = "Set user {user_id} note to: {note}"
    RETENTION_SET_SUCCESS: str = "Set user {user_id} history retention to {days} days"

    NO_RECORDS_IN_DAYS: str = "No chat records in the last {days} days"
    ALL_USERS_STATS_TITLE: str = "All Users Statistics (Last {days} days)"
    TOTAL_LABEL: str = "Total"
    DAILY_AVG_LABEL: str = "Daily avg"
    ERRORS_LABEL: str = "Errors"
    MESSAGES_UNIT: str = "msgs"
    TIMES: str = "times"

    USER_STATS_TITLE: str = "User {name} Statistics (Last {days} days)"
    ERROR_LABEL: str = "error"
    TODAY_ACTIVE_HOURS: str = "Today's active hours"
    HOUR_SUFFIX: str = "h"

    USER_HISTORY_TITLE: str = "User {name} Last {count} Conversations"
    NO_HISTORY: str = "User {user_id} has no chat history"

    CLEANUP_DONE: str = "Cleanup completed:"
    DELETED_RECORDS: str = "deleted {count} records"
    NO_CLEANUP_NEEDED: str = "No records need to be cleaned up"

    # ===== Message Processing =====
    PROCESSING: str = "Processing..."
    STEP_PROGRESS: str = "Step {step}: {tool}..."
    PROCESS_FAILED: str = "Processing failed: {error}"

    # ===== File Upload =====
    RECEIVING_FILE: str = "Receiving file..."
    FILE_SAVED: str = "File saved: {name} ({size})"
    FILE_TOO_LARGE: str = "File too large, cannot send (exceeds 50MB)"
    PROCESS_FILE_FAILED: str = "Failed to process file: {error}"
    LONG_RESPONSE_CAPTION: str = "Response is too long, converted to file"

    FILE_UPLOAD_PROMPT: str = """User uploaded a file:
- Filename: {filename}
- Size: {size}
- Saved to: uploads/{filename}
{caption_line}

Please help the user process this file. If it's a document (PDF, Word, TXT, etc.), you can read and summarize its content."""
    USER_CAPTION_LINE: str = "- User note: {caption}"

    # ===== Tool Names (for progress display) =====
    TOOL_READ: str = "Reading file"
    TOOL_WRITE: str = "Writing file"
    TOOL_EDIT: str = "Editing file"
    TOOL_GLOB: str = "Searching files"
    TOOL_GREP: str = "Searching content"
    TOOL_SKILL: str = "Executing skill"
    TOOL_SEND_MESSAGE: str = "Sending message"
    TOOL_SEND_FILE: str = "Sending file"
    TOOL_WEB_SEARCH: str = "Searching web"
    TOOL_WEB_FETCH: str = "Fetching webpage"
    TOOL_PDF_TO_MD: str = "PDF to Markdown"
    TOOL_DELETE_FILE: str = "Deleting file"
    TOOL_COMPRESS: str = "Compressing folder"
    TOOL_DELEGATE: str = "Delegating task"
    TOOL_DELEGATE_REVIEW: str = "Delegating review task"
    TOOL_SCHEDULE_LIST: str = "Listing schedules"
    TOOL_SCHEDULE_GET: str = "Getting schedule"
    TOOL_SCHEDULE_CREATE: str = "Creating schedule"
    TOOL_SCHEDULE_UPDATE: str = "Updating schedule"
    TOOL_SCHEDULE_DELETE: str = "Deleting schedule"

    # ===== Tool Error Messages =====
    ERR_EMPTY_MESSAGE: str = "Error: Message content cannot be empty"
    ERR_SEND_MESSAGE_FAILED: str = "Failed to send message: {error}"
    MESSAGE_SENT: str = "Message sent: {preview}..."

    ERR_EMPTY_FILE_PATH: str = "Error: File path cannot be empty"
    FILE_SENT: str = "File sent: {path}"
    FILE_SEND_FAILED: str = "File sending failed: {path}"
    ERR_SEND_FILE_FAILED: str = "Failed to send file: {error}"

    ERR_EMPTY_QUERY: str = "Error: Search query cannot be empty"
    NO_SEARCH_RESULTS: str = "No results found for '{query}'"
    SEARCH_RESULTS_FOR: str = "Search results for '{query}':"
    LINK_LABEL: str = "Link"
    SNIPPET_LABEL: str = "Summary"
    SEARCH_FAILED: str = "Search failed: {error}"

    ERR_EMPTY_URL: str = "Error: URL cannot be empty"
    WEBPAGE_CONTENT: str = "Webpage content ({url}):"
    CONTENT_TRUNCATED: str = "[Content truncated]"
    FETCH_FAILED: str = "Failed to fetch webpage: {error}"

    ERR_EMPTY_PDF_PATH: str = "Error: PDF file path cannot be empty"
    ERR_PDF_SERVICE_NOT_CONFIGURED: str = "Error: PDF conversion service not configured"
    ERR_PDF_NOT_EXIST: str = "Error: PDF file does not exist: {path}"
    PDF_CONVERSION_DONE: str = "PDF conversion complete!"
    PDF_MD_FILE: str = "Markdown file"
    PDF_IMAGE_COUNT: str = "Image count"
    PDF_IMAGE_DIR: str = "Image directory"
    PDF_TOTAL_PAGES: str = "Total pages"
    PDF_CONVERSION_FAILED: str = "PDF conversion failed: {error}"

    ERR_WORKING_DIR_NOT_SET: str = "Error: Working directory not configured"
    ERR_ONLY_WORKING_DIR: str = "Error: Can only operate on files within working directory"
    ERR_FILE_NOT_EXIST: str = "Error: File does not exist: {path}"
    ERR_CANNOT_DELETE_DIR: str = "Error: Cannot delete directory, only files"
    FILE_DELETED: str = "File deleted: {path}"
    DELETE_FAILED: str = "Failed to delete file: {error}"

    ERR_EMPTY_FOLDER_PATH: str = "Error: Folder path cannot be empty"
    ERR_ONLY_COMPRESS_WORKING_DIR: str = "Error: Can only compress folders within working directory"
    ERR_FOLDER_NOT_EXIST: str = "Error: Folder does not exist: {path}"
    ERR_NOT_A_FOLDER: str = "Error: Specified path is not a folder"
    ERR_OUTPUT_MUST_BE_IN_WORKING_DIR: str = "Error: Output path must be within working directory"
    COMPRESS_DONE: str = "Compression complete!"
    COMPRESS_RESULT: str = "Compression complete!\n- Archive: {path}\n- Files: {count}\n- Size: {size}"
    ARCHIVE_FILE: str = "Archive"
    FILE_COUNT: str = "Files"
    SIZE_LABEL: str = "Size"
    COMPRESS_FAILED: str = "Failed to compress folder: {error}"

    # ===== Tool Descriptions (for Agent) =====
    TOOL_DESC_SEND_MESSAGE: str = "Send message to Telegram chat. Use to report progress, results, or ask questions."
    TOOL_DESC_SEND_FILE: str = "Send file to Telegram chat. File must be within the working directory."
    TOOL_DESC_WEB_SEARCH: str = "Search the internet for latest information. Uses DuckDuckGo search engine. Returns list of results with title, link, and summary."
    TOOL_DESC_WEB_FETCH: str = "Fetch webpage content. Input URL, returns text content with HTML tags removed."
    TOOL_DESC_PDF_TO_MD: str = "Convert PDF file to Markdown format with image extraction. Input PDF path (within user directory), outputs Markdown file and images folder."
    TOOL_DESC_DELETE_FILE: str = "Delete specified file. Can only delete files within working directory, cannot delete directories."
    TOOL_DESC_COMPRESS_FOLDER: str = "Compress folder to ZIP archive. Must compress before sending entire folders."
    TOOL_DESC_DELEGATE_TASK: str = "Delegate a task to a Sub Agent for background processing. Use for research, analysis, or other time-consuming tasks. Returns task ID."

    # ===== Orchestrator Messages =====
    MESSAGE_MERGED: str = "Received new message, merging with previous..."
    WAITING_SUB_AGENTS: str = "Working on {count} background tasks..."
    SUB_AGENT_RESULTS_HEADER: str = "Background task results:"
    SYNTHESIZE_RESULTS_PROMPT: str = "Please synthesize the following background task results and provide a comprehensive response to the user:\n\n{results}"
    DELEGATE_TASK_CREATED: str = "Task delegated (ID: {task_id}): {description}"
    DELEGATE_REVIEW_TASK_CREATED: str = "Review task created (ID: {task_id}): {description}\n\nThis task will be automatically reviewed after completion. You'll receive progress updates."
    DELEGATE_TASK_LIMIT: str = "Cannot create more background tasks (limit: {limit})"
    AGENT_BUSY: str = "I'm currently processing. Your message has been queued and will be handled shortly."
    TASK_CANCELLED: str = "Previous task cancelled due to new message"
    TASK_COMPLETED: str = "Background task completed"
    RESULT_TRUNCATED: str = "Result truncated, check files for full content"

    # ===== Review System Messages =====
    REVIEW_TASK_RESULT: str = "Task result [{attempt}/{max_attempts}]:\n\n{result}"
    REVIEW_PASSED: str = "Review passed!"
    REVIEW_REJECTED: str = "Retry #{count}\nIssue: {feedback}\nRetrying..."
    REVIEW_MAX_RETRIES: str = "Max retries ({max}) reached. Returning final result."
    REVIEW_TASK_FAILED: str = "Task execution failed: {error}"

    # ===== Schedule =====
    SCHEDULE_HELP: str = """定时任务管理

命令:
/schedule list        - 查看所有任务
/schedule add ...     - 创建任务 (见下方格式)
/schedule del <id>    - 删除任务
/schedule enable <id> - 启用任务
/schedule disable <id> - 禁用任务
/schedule reset <id>  - 重置已完成任务
/schedule info <id>   - 查看任务详情
/schedule edit <id>   - 修改任务指令
/schedule timezone    - 设置时区

创建任务格式:
/schedule add <ID> <类型> <参数> [--max N] <名称>

支持的类型:
  daily    HH:MM              - 每天
  weekly   HH:MM 星期         - 每周
  monthly  HH:MM 日期         - 每月
  interval 30m/2h/1d         - 间隔
  once     YYYY-MM-DD HH:MM  - 一次性

示例:
/schedule add news daily 09:00 每日新闻
/schedule add test daily 09:00 --max 3 测试"""

    SCHEDULE_LIST_TITLE: str = "Your Scheduled Tasks"
    SCHEDULE_LIST_EMPTY: str = "No scheduled tasks. Use /schedule add to create one."
    SCHEDULE_TIMEZONE_LABEL: str = "Timezone"
    SCHEDULE_TASK_FORMAT: str = "{status} {name}\n   ID: {task_id}\n   Time: {time}\n   Last run: {last_run}"
    SCHEDULE_ENABLED: str = "ON"
    SCHEDULE_DISABLED: str = "OFF"
    SCHEDULE_NEVER_RUN: str = "Never"

    SCHEDULE_ADD_WAITING_PROMPT: str = "Task created (not active yet): {name}\nID: {task_id}\nTime: {time} ({timezone})\n\nNow send me the prompt/instructions for this task.\nSend /cancel to abort."
    SCHEDULE_ADD_INVALID_TIME: str = "Invalid time format. Use HH:MM (e.g., 09:00, 14:30)"
    SCHEDULE_ADD_INVALID_ID: str = "Invalid task ID. Use only letters, numbers, and underscores."
    SCHEDULE_ADD_ID_TOO_LONG: str = "Task ID too long. Maximum 32 characters allowed."
    SCHEDULE_ADD_EXISTS: str = "Task with ID '{task_id}' already exists"
    SCHEDULE_ADD_USAGE: str = "Usage: /schedule add <task_id> <HH:MM> <task name>\nExample: /schedule add daily_news 09:00 Daily News Summary"
    SCHEDULE_ADD_USAGE_NEW: str = """定时任务创建格式:

/schedule add <ID> <类型> <参数> [--max N] <名称>

类型和参数:
  daily    HH:MM              每天执行
  weekly   HH:MM mon,wed,fri  每周指定日执行
  monthly  HH:MM 15           每月指定日执行
  interval 30m/2h/1d          按间隔执行
  once     YYYY-MM-DD HH:MM   一次性执行

示例:
  /schedule add news daily 09:00 每日新闻
  /schedule add report weekly 10:00 mon,fri 周报
  /schedule add check interval 2h 定时检查
  /schedule add remind once 2025-02-01 09:00 提醒
  /schedule add test daily 09:00 --max 3 测试任务"""

    SCHEDULE_DEL_SUCCESS: str = "Deleted scheduled task: {task_id}"
    SCHEDULE_DEL_NOT_FOUND: str = "Task not found: {task_id}"
    SCHEDULE_DEL_USAGE: str = "Usage: /schedule del <task_id>"

    SCHEDULE_ENABLE_SUCCESS: str = "Enabled task: {task_id}"
    SCHEDULE_DISABLE_SUCCESS: str = "Disabled task: {task_id}"
    SCHEDULE_TOGGLE_NOT_FOUND: str = "Task not found: {task_id}"

    SCHEDULE_TIMEZONE_SUCCESS: str = "Timezone set to: {timezone}"
    SCHEDULE_TIMEZONE_INVALID: str = "Invalid timezone: {timezone}\nExamples: Asia/Shanghai, America/New_York, Europe/London"
    SCHEDULE_TIMEZONE_CURRENT: str = "Current timezone: {timezone}\nUse /schedule timezone <tz> to change"

    SCHEDULE_EDIT_PROMPT: str = "Current prompt for task '{task_id}':\n\n{prompt}\n\nSend new prompt to update, or /cancel to abort."
    SCHEDULE_EDIT_SUCCESS: str = "Updated prompt for task: {task_id}"
    SCHEDULE_EDIT_NOT_FOUND: str = "Task not found: {task_id}"

    SCHEDULE_RUN_STARTED: str = "Running scheduled task: {name}"
    SCHEDULE_RUN_QUEUED: str = "Task queued (Sub Agents busy): {name}"

    SCHEDULE_PROMPT_SAVED: str = "Prompt saved for task: {task_id}\nTask is now active and will run at the scheduled time."
    SCHEDULE_PROMPT_SAVE_FAILED: str = "Failed to save prompt for task: {task_id}"
    SCHEDULE_PROMPT_CANCELLED: str = "Cancelled. Task '{task_id}' has been deleted."

    # ===== Skills =====
    SKILL_HELP: str = """Custom Skills Management

Commands:
/skill list - List your installed skills
/skill del <name> - Delete a skill
/skill info <name> - View skill details

To install a skill:
Upload a .zip file containing SKILL.md and reply with "install skill" or use caption "skill"

Skill format requirements:
- Must contain SKILL.md file
- SKILL.md must have YAML frontmatter with name and description
- No executable code or prompt injection allowed"""

    SKILL_LIST_TITLE: str = "Your Installed Skills"
    SKILL_LIST_EMPTY: str = "No skills installed.\n\nUpload a .zip file with SKILL.md to install a skill."
    SKILL_NOT_FOUND: str = "Skill not found: {name}"
    SKILL_DELETED: str = "Skill deleted: {name}"
    SKILL_DEL_USAGE: str = "Usage: /skill del <skill_name>"
    SKILL_INFO_USAGE: str = "Usage: /skill info <skill_name>"

    SKILL_INSTALL_START: str = "Validating skill package..."
    SKILL_INSTALL_SUCCESS: str = "Skill installed: {name}\n\n{description}"
    SKILL_INSTALL_FAILED: str = "Skill installation failed"
    SKILL_VALIDATION_ERRORS: str = "Validation errors:"
    SKILL_VALIDATION_WARNINGS: str = "Warnings:"
    SKILL_FIX_SUGGESTIONS: str = "Suggestions to fix:"

    SKILL_UPLOAD_HINT: str = "This looks like a skill package. Reply 'install' to install it, or 'cancel' to skip."
    SKILL_UPLOAD_CANCELLED: str = "Skill installation cancelled."


# Singleton instance
_strings: Strings | None = None


def get_strings(lang: str = "en") -> Strings:
    """
    Get strings instance for the specified language.

    Args:
        lang: Language code (e.g., "en", "zh"). Currently only "en" is supported.

    Returns:
        Strings instance with all user-facing text
    """
    global _strings

    # Currently only English is supported
    # Future: Add language switching logic here
    # if lang == "zh":
    #     return StringsZH()

    if _strings is None:
        _strings = Strings()
    return _strings


def t(key: str, **kwargs) -> str:
    """
    Get translated string by key with optional format arguments.

    Args:
        key: The attribute name in Strings class
        **kwargs: Format arguments for the string

    Returns:
        Translated and formatted string

    Example:
        t("FILE_SAVED", name="test.txt", size="1.2 KB")
        # Returns: "File saved: test.txt (1.2 KB)"
    """
    strings = get_strings()
    text = getattr(strings, key, key)
    if kwargs:
        try:
            return text.format(**kwargs)
        except KeyError:
            return text
    return text


# Tool name mapping for progress display
TOOL_NAMES: Dict[str, str] = {
    "Read": "TOOL_READ",
    "Write": "TOOL_WRITE",
    "Edit": "TOOL_EDIT",
    "Glob": "TOOL_GLOB",
    "Grep": "TOOL_GREP",
    "Skill": "TOOL_SKILL",
    "mcp__telegram__send_telegram_message": "TOOL_SEND_MESSAGE",
    "mcp__telegram__send_telegram_file": "TOOL_SEND_FILE",
    "mcp__telegram__web_search": "TOOL_WEB_SEARCH",
    "mcp__telegram__web_fetch": "TOOL_WEB_FETCH",
    "mcp__telegram__pdf_to_markdown": "TOOL_PDF_TO_MD",
    "mcp__telegram__delete_file": "TOOL_DELETE_FILE",
    "mcp__telegram__compress_folder": "TOOL_COMPRESS",
    "mcp__telegram__delegate_task": "TOOL_DELEGATE",
    "mcp__telegram__delegate_and_review": "TOOL_DELEGATE_REVIEW",
    "mcp__telegram__schedule_list": "TOOL_SCHEDULE_LIST",
    "mcp__telegram__schedule_get": "TOOL_SCHEDULE_GET",
    "mcp__telegram__schedule_create": "TOOL_SCHEDULE_CREATE",
    "mcp__telegram__schedule_update": "TOOL_SCHEDULE_UPDATE",
    "mcp__telegram__schedule_delete": "TOOL_SCHEDULE_DELETE",
}


def get_tool_display_name(tool_name: str) -> str:
    """
    Get display name for a tool.

    Args:
        tool_name: Internal tool name

    Returns:
        User-friendly display name
    """
    strings = get_strings()
    key = TOOL_NAMES.get(tool_name)
    if key:
        return getattr(strings, key, tool_name)
    return tool_name
