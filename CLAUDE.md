# Telegram File Management Bot with Claude Agent

## IMPORTANT: Changelog Requirement

**每次完成功能修改、bug 修复或优化后，必须更新 CHANGELOG.md：**
1. 在文件最上方添加新条目（最新的在最上面）
2. 格式：`## [YYYY-MM-DD] 简短标题`
3. 包含：新增功能、修改文件、修复的问题
4. 如果是修复之前的问题，注明是对哪次修改的修复

## Project Overview

This is a multi-user Telegram bot that provides file management and AI assistant capabilities powered by Claude Agent SDK. Users can interact with Claude through Telegram to manage files, get AI assistance, and upload documents for analysis.

## Architecture

```
telegram bot/
├── main.py              # Entry point, loads config and starts bot
├── config.json          # Configuration (tokens, API keys, paths)
├── requirements.txt     # Python dependencies
├── Dockerfile           # Container build config
├── docker-compose.yml   # Container orchestration
├── entrypoint.sh        # Container startup script
└── bot/
    ├── __init__.py      # Exports: setup_handlers, UserManager, SessionManager
    ├── handlers.py      # Telegram command handlers and message processing
    ├── file_manager.py  # File operations utility
    ├── agent/
    │   ├── __init__.py
    │   ├── client.py    # TelegramAgentClient - Claude Agent SDK wrapper
    │   └── tools.py     # MCP tools (send_telegram_message, send_telegram_file)
    ├── user/
    │   ├── __init__.py
    │   ├── manager.py   # UserManager - user lifecycle and config
    │   ├── storage.py   # Storage quota management
    │   └── environment.py # User environment variables
    └── session/
        ├── __init__.py
        └── manager.py   # SessionManager - conversation session persistence
```

## Key Components

### TelegramAgentClient (`bot/agent/client.py`)
- Wraps Claude Agent SDK for Telegram integration
- Creates MCP server with Telegram-specific tools
- Handles session resume via `options.resume = session_id`
- Implements storage quota checks via PreToolUse hooks
- Uses `setting_sources=["user", "project"]` to load Claude Skills

### Handlers (`bot/handlers.py`)
- `/start`, `/help` - Welcome and help messages
- `/ls [path]` - List directory contents
- `/storage` - View storage quota
- `/session` - View current session status
- `/new` - Start new conversation (clear context)
- `/env` - Manage environment variables
- `/packages` - Python package management
- `/admin` - Admin commands (users, sessions, quotas)
- Text messages -> Claude Agent processing
- Document uploads -> Save to uploads/ and notify Agent

### Session Management (`bot/session/manager.py`)
- 30-minute timeout (configurable)
- Persists sessions to JSON file
- Supports session resume for conversation continuity

### User Management (`bot/user/`)
- Multi-user isolation with separate storage directories
- 5GB default storage quota per user
- Environment variable management per user
- Admin/user permission system

## Configuration

`config.json` structure:
```json
{
    "bot_token": "TELEGRAM_BOT_TOKEN",
    "admin_users": [USER_ID],
    "users_data_directory": "/app/users",  // MUST be container path for Docker
    "default_quota_gb": 5.0,
    "allow_new_users": true,
    "anthropic_api_key": "...",
    "anthropic_base_url": "https://...",  // Do NOT include /v1 suffix
    "claude_model": "claude-sonnet-4-5-20250929"
}
```

**CRITICAL**: `users_data_directory` must be `/app/users` (container path) when running in Docker, not the host path. The host `./users` directory is mounted to `/app/users` in the container.

**CRITICAL**: `anthropic_base_url` should NOT include `/v1` suffix - the SDK adds it automatically.

## Docker Deployment

**IMPORTANT: Use `docker compose` (with space), NOT `docker-compose` (with hyphen). This system uses Docker Compose v2.**

Build and run (REQUIRED after ANY code changes):
```bash
docker compose up --build -d
```

Restart without rebuild (ONLY for config.json changes, NOT code changes):
```bash
docker compose restart
```

**CRITICAL: `restart` does NOT update code! Always use `up --build` after modifying .py files!**

View logs:
```bash
docker compose logs -f
```

Volume mounts:
- `./users:/app/users` - User data persistence
- `./config.json:/app/config.json:ro` - Configuration

## Skills System

Skills are defined in `.claude/skills/*/SKILL.md` and loaded via `setting_sources=["user", "project"]`. The entrypoint.sh copies skills from `/app/.claude/skills` to `~/.claude/skills` at container startup.

Current skills:
- `document-analysis` - Analyze uploaded documents (PDF, TXT, Word)
- `web-research` - Search web for information

## Claude Agent Integration

Allowed tools for the Agent:
- `mcp__telegram__send_telegram_message` - Send text to user
- `mcp__telegram__send_telegram_file` - Send file to user
- `Read`, `Write`, `Edit` - File operations
- `Glob`, `Grep` - File search
- `WebSearch`, `WebFetch` - Web access
- `Skill` - Execute Claude Skills

Disallowed: `Bash` (security)

## System Prompt Features

The Agent is configured with:
- yrzhe branding (creator attribution + Twitter link)
- Telegram formatting rules (no markdown bold/italic)
- File organization guidelines (uploads/, documents/, analysis/, etc.)
- Storage quota awareness
- Chinese language preference

## Important Notes

1. **Long messages** (>2000 chars) are automatically sent as .txt files
2. **File uploads** are saved to user's `uploads/` directory
3. **Session timeout** is 30 minutes of inactivity
4. **Storage quota** is enforced via PreToolUse hooks
5. **docs/** folder is on host filesystem - changes don't require Docker rebuild
