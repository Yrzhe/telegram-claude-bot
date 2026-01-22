# Telegram Claude Bot

A multi-user Telegram bot powered by Claude Agent SDK, featuring AI conversations, file management, and intelligent assistant capabilities.

[中文文档](./README_CN.md)

## Features

- **AI Conversations** - Powered by Claude Agent SDK with multi-turn dialogue and session memory
- **Multi-User Support** - User isolation with independent storage space and configuration
- **File Management** - Upload, download, and organize files with document analysis support
- **User Preference Memory** - Automatically remembers user preferences and instructions
- **Scheduled Tasks** - Set up scheduled tasks (e.g., scheduled news push)
- **Custom Commands** - Users can create custom shortcut commands
- **Storage Quota** - 5GB storage quota per user (configurable)
- **Web Search** - Real-time web search for up-to-date information

## Quick Start

### Prerequisites

- Docker and Docker Compose
- Telegram Bot Token (get from [@BotFather](https://t.me/BotFather))
- Anthropic API Key

### Installation

1. **Clone the repository**

```bash
git clone https://github.com/Yrzhe/telegram-claude-bot.git
cd telegram-claude-bot
```

2. **Create configuration file**

```bash
cp config.example.json config.json
```

3. **Edit configuration**

```json
{
    "bot_token": "YOUR_TELEGRAM_BOT_TOKEN",
    "admin_users": [YOUR_TELEGRAM_USER_ID],
    "users_data_directory": "/app/users",
    "default_quota_gb": 5.0,
    "allow_new_users": true,
    "session_timeout_minutes": 60,
    "anthropic_api_key": "YOUR_ANTHROPIC_API_KEY",
    "anthropic_base_url": "https://api.anthropic.com",
    "claude_model": "claude-sonnet-4-5-20250929"
}
```

> **Note**: `anthropic_base_url` should NOT include the `/v1` suffix

4. **Start the service**

```bash
docker compose up --build -d
```

5. **View logs**

```bash
docker compose logs -f
```

## Commands

| Command | Description |
|---------|-------------|
| `/start` | Start using the bot |
| `/help` | Display help information |
| `/new` | Start a new conversation (clear context) |
| `/ls [path]` | List directory contents |
| `/storage` | View storage usage |
| `/session` | View current session status |
| `/env` | Manage environment variables |
| `/packages` | Manage Python packages |
| `/admin` | Admin commands |

## Project Structure

```
telegram-claude-bot/
├── main.py              # Entry point
├── config.json          # Configuration (not committed)
├── config.example.json  # Configuration template
├── requirements.txt     # Python dependencies
├── Dockerfile
├── docker-compose.yml
├── system_prompt.txt    # Claude system prompt
└── bot/
    ├── handlers.py      # Telegram command handlers
    ├── file_manager.py  # File operations
    ├── i18n.py          # Internationalization
    ├── agent/           # Claude Agent integration
    │   ├── client.py    # Agent client
    │   ├── tools.py     # MCP tool definitions
    │   └── ...
    ├── user/            # User management
    │   ├── manager.py   # User lifecycle
    │   ├── storage.py   # Storage quota
    │   └── ...
    ├── session/         # Session management
    ├── schedule/        # Scheduled tasks
    ├── skill/           # Skills system
    └── custom_command/  # Custom commands
```

## Development

### Redeploy after code changes

```bash
docker compose up --build -d
```

> **Important**: You MUST use the `--build` flag after code changes. `docker compose restart` does NOT update the code!

### Restart after configuration changes only

```bash
docker compose restart
```

## Configuration Reference

| Option | Description |
|--------|-------------|
| `bot_token` | Telegram Bot Token |
| `admin_users` | List of admin user IDs |
| `users_data_directory` | User data directory (use `/app/users` in Docker) |
| `default_quota_gb` | Default storage quota (GB) |
| `allow_new_users` | Whether to allow new users |
| `session_timeout_minutes` | Session timeout (minutes) |
| `anthropic_api_key` | Anthropic API key |
| `anthropic_base_url` | API URL (without `/v1`) |
| `claude_model` | Model to use |

## License

MIT

## Author

Created by [yrzhe](https://x.com/yrzhe_top)
