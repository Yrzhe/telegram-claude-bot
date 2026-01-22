# Telegram Claude Bot

一个基于 Claude Agent SDK 的多用户 Telegram 机器人，提供 AI 对话、文件管理和智能助手功能。

[English](./README.md)

## 功能特性

- **AI 对话** - 基于 Claude Agent SDK，支持多轮对话和会话记忆
- **多用户支持** - 用户隔离，独立存储空间和配置
- **文件管理** - 上传、下载、组织文件，支持文档分析
- **用户偏好记忆** - 自动记住用户的偏好和指令
- **定时任务** - 支持设置定时任务（如定时推送新闻）
- **自定义命令** - 用户可创建自定义快捷命令
- **存储配额** - 每用户 5GB 存储配额（可配置）
- **网络搜索** - 支持实时网络搜索获取最新信息

## 快速开始

### 前置要求

- Docker 和 Docker Compose
- Telegram Bot Token（从 [@BotFather](https://t.me/BotFather) 获取）
- Anthropic API Key

### 安装部署

1. **克隆仓库**

```bash
git clone https://github.com/Yrzhe/telegram-claude-bot.git
cd telegram-claude-bot
```

2. **创建配置文件**

```bash
cp config.example.json config.json
```

3. **编辑配置**

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

> **注意**: `anthropic_base_url` 不要包含 `/v1` 后缀

4. **启动服务**

```bash
docker compose up --build -d
```

5. **查看日志**

```bash
docker compose logs -f
```

## 命令列表

| 命令 | 说明 |
|------|------|
| `/start` | 开始使用机器人 |
| `/help` | 显示帮助信息 |
| `/new` | 开始新对话（清除上下文） |
| `/ls [path]` | 列出目录内容 |
| `/storage` | 查看存储使用情况 |
| `/session` | 查看当前会话状态 |
| `/env` | 管理环境变量 |
| `/packages` | 管理 Python 包 |
| `/admin` | 管理员命令 |

## 项目结构

```
telegram-claude-bot/
├── main.py              # 入口文件
├── config.json          # 配置文件（不上传）
├── config.example.json  # 配置模板
├── requirements.txt     # Python 依赖
├── Dockerfile
├── docker-compose.yml
├── system_prompt.txt    # Claude 系统提示词
└── bot/
    ├── handlers.py      # Telegram 命令处理
    ├── file_manager.py  # 文件操作
    ├── i18n.py          # 国际化
    ├── agent/           # Claude Agent 集成
    │   ├── client.py    # Agent 客户端
    │   ├── tools.py     # MCP 工具定义
    │   └── ...
    ├── user/            # 用户管理
    │   ├── manager.py   # 用户生命周期
    │   ├── storage.py   # 存储配额
    │   └── ...
    ├── session/         # 会话管理
    ├── schedule/        # 定时任务
    ├── skill/           # 技能系统
    └── custom_command/  # 自定义命令
```

## 开发

### 修改代码后重新部署

```bash
docker compose up --build -d
```

> **重要**: 修改代码后必须使用 `--build` 参数，`docker compose restart` 不会更新代码！

### 仅修改配置后重启

```bash
docker compose restart
```

## 配置说明

| 配置项 | 说明 |
|--------|------|
| `bot_token` | Telegram Bot Token |
| `admin_users` | 管理员用户 ID 列表 |
| `users_data_directory` | 用户数据目录（Docker 中使用 `/app/users`） |
| `default_quota_gb` | 默认存储配额（GB） |
| `allow_new_users` | 是否允许新用户 |
| `session_timeout_minutes` | 会话超时时间（分钟） |
| `anthropic_api_key` | Anthropic API 密钥 |
| `anthropic_base_url` | API 地址（不含 `/v1`） |
| `claude_model` | 使用的模型 |

## License

MIT

## 作者

Created by [yrzhe](https://x.com/yrzhe_top)
