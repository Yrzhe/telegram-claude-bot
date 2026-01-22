# Telegram Claude Agent Bot 开发历程

> 作者：yrzhe
> 日期：2026年1月7日
> 这是一篇记录如何与 AI 协作开发的完整过程，包括想法、决策、问题解决和经验分享。

---

## 目录

1. [项目起源与初始想法](#1-项目起源与初始想法)
2. [技术选型与架构设计](#2-技术选型与架构设计)
3. [Claude Agent SDK 集成](#3-claude-agent-sdk-集成)
4. [多用户支持与隔离](#4-多用户支持与隔离)
5. [自定义 API Gateway 配置](#5-自定义-api-gateway-配置)
6. [Docker 部署与会话持久化](#6-docker-部署与会话持久化)
7. [问题排查与解决](#7-问题排查与解决)
8. [功能迭代与优化](#8-功能迭代与优化)
9. [Skills 系统集成](#9-skills-系统集成)
10. [经验总结与 AI 协作心得](#10-经验总结与-ai-协作心得)

---

## 1. 项目起源与初始想法

### 1.1 需求背景

我想在 VPS 上创建一个 Telegram Bot，实现以下核心功能：
- 通过 Telegram 消息与 AI 助手交互
- AI 能够管理我的文件（读取、创建、编辑、删除）
- AI 能够获取文件地址并下载文件
- 权限限制在特定文件夹内，保证安全

### 1.2 初始对话

**我的第一条消息：**
> "这个文件夹我想接一个 telegram bot，就是这个 bot 能够获取我的文件地址以及下载文件..."

**关键决策点：**
1. 选择编程语言 → 选择了 Python（熟悉度高、生态丰富）
2. 文件操作权限 → 限制在 `/root/telegram bot/files` 目录内
3. 代码结构 → 模块化设计，方便后续维护

### 1.3 模块化设计理念

我强调了模块化的重要性：
> "注意要分模块来构建，这样方便后续维护"

最终的模块结构：
```
bot/
├── __init__.py          # 模块导出
├── handlers.py          # Telegram 命令处理
├── agent/               # Claude Agent 相关
│   ├── client.py        # Agent 客户端
│   └── tools.py         # 自定义工具
├── user/                # 用户管理
│   ├── manager.py       # 用户管理器
│   ├── storage.py       # 存储配额
│   └── environment.py   # 环境隔离
└── session/             # 会话管理
    └── manager.py       # 会话持久化
```

---

## 2. 技术选型与架构设计

### 2.1 核心技术栈

| 组件 | 技术选择 | 原因 |
|------|----------|------|
| Bot 框架 | python-telegram-bot | 成熟稳定，异步支持好 |
| AI 集成 | Claude Agent SDK | 官方 SDK，功能强大 |
| 部署方式 | Docker | 隔离性好，便于管理 |
| 配置管理 | JSON 文件 | 简单直观，易于修改 |

### 2.2 配置文件设计

`config.json` 的演进过程：

**初始版本：**
```json
{
    "bot_token": "YOUR_BOT_TOKEN",
    "allowed_directory": "/root/telegram bot/files"
}
```

**最终版本：**
```json
{
    "bot_token": "YOUR_BOT_TOKEN",
    "admin_users": [YOUR_USER_ID],
    "users_data_directory": "/root/telegram bot/users",
    "default_quota_gb": 5.0,
    "allow_new_users": true,
    "anthropic_api_key": "YOUR_API_KEY",
    "anthropic_base_url": "https://api.anthropic.com",
    "claude_model": "claude-sonnet-4-5-20250929"
}
```

**设计思考：**
- 将敏感信息（API Key、Bot Token）集中管理
- 支持多管理员
- 可配置的用户配额
- 灵活的 API 端点配置

---

## 3. Claude Agent SDK 集成

### 3.1 集成方式的选择

AI 提供了三种集成方案：

1. **简单集成** - Agent 只返回文本，Bot 转发
2. **中等集成** - Agent 发送消息，支持简单格式
3. **完全集成** - Agent 主动发送消息和文件（MCP 工具）

**我的选择：** 方案3 - 完全集成

**原因：**
- Agent 可以主动向用户发送消息和文件
- 更自然的交互体验
- 充分发挥 Agent 的能力

### 3.2 自定义 MCP 工具

为了让 Agent 能主动与 Telegram 交互，创建了两个 MCP 工具：

```python
# tools.py
@server.tool()
async def send_telegram_message(message: str) -> str:
    """向用户发送 Telegram 消息"""

@server.tool()
async def send_telegram_file(file_path: str, caption: str = None) -> str:
    """向用户发送文件"""
```

### 3.3 Agent 配置

```python
options = ClaudeAgentOptions(
    cwd=str(self.working_directory),
    mcp_servers={"telegram": self.mcp_server},
    allowed_tools=[
        "mcp__telegram__send_telegram_message",
        "mcp__telegram__send_telegram_file",
        "Read", "Write", "Edit", "Glob", "Grep",
        "WebSearch", "WebFetch", "Skill",
    ],
    disallowed_tools=["Bash"],  # 安全考虑，禁用 Bash
    permission_mode="acceptEdits",
    setting_sources=["user", "project"],  # 加载 Skills
)
```

---

## 4. 多用户支持与隔离

### 4.1 需求演进

最初是单用户设计，后来我提出了多用户需求：

> "每个用户需要有自己的文件存储区域、独立的 Agent 会话、隔离的环境"

### 4.2 用户隔离方案

**目录结构：**
```
users/
├── <user_id>/
│   ├── data/           # 用户文件
│   │   ├── uploads/    # 上传的文件
│   │   ├── documents/  # 文档
│   │   ├── analysis/   # 分析结果
│   │   └── ...
│   └── .env            # 用户环境变量
├── users.json          # 用户配置
└── sessions.json       # 会话数据
```

**存储配额系统：**
```python
class UserManager:
    def __init__(self, base_path: str, default_quota_gb: float = 5.0):
        self.default_quota_gb = default_quota_gb

    def get_user_storage_info(self, user_id: int) -> dict:
        # 返回已使用空间、配额、剩余空间等
```

### 4.3 管理员功能

添加了管理员专属命令：
- `/admin list` - 查看所有用户
- `/admin quota <user_id> <GB>` - 设置用户配额
- `/admin block/unblock <user_id>` - 封禁/解封用户

---

## 5. 自定义 API Gateway 配置

### 5.1 问题背景

我使用的是自己的 API Gateway，不是官方 Anthropic API。

**配置信息示例：**
```json
{
  "custom-gateway": {
    "baseURL": "https://your-gateway.example.com/v1",
    "models": {
      "claude-sonnet-4-5-20250929": {"name": "claude-sonnet-4.5"}
    }
  }
}
```

### 5.2 遇到的问题

**错误信息：**
```
API Error: 400 {"error":{"message":"Unknown Gemini action: v1/messages"}}
```

**排查过程：**

1. **首先测试 API 是否可用** - 用 curl 测试成功
   ```bash
   curl -X POST "https://your-gateway.example.com/v1/messages" \
     -H "x-api-key: YOUR_API_KEY" \
     -H "anthropic-version: 2023-06-01" \
     -d '{"model": "claude-sonnet-4-5-20250929", ...}'
   # 成功！
   ```

2. **问题定位** - SDK 和 CLI 使用不同的 URL 拼接方式
   - SDK 会自动添加 `/v1/messages`
   - 如果 base_url 已经包含 `/v1`，就会变成 `/v1/v1/messages`

3. **解决方案** - base_url 不要包含 `/v1`
   ```json
   "anthropic_base_url": "https://your-gateway.example.com"
   ```

### 5.3 经验教训

> **重要发现：** Anthropic SDK 的 `base_url` 参数不应包含 `/v1` 后缀，SDK 会自动添加路径。

这个问题花了不少时间排查，教训是：
1. 先用最简单的方式（curl）测试 API
2. 对比成功和失败请求的差异
3. 理解 SDK 内部的 URL 拼接逻辑

---

## 6. Docker 部署与会话持久化

### 6.1 为什么要 Docker 化

我的考虑：

> "假如我退出关闭我们这次对话，这个程序还会一直运行吗？我担心 Claude Agent 在执行一些任务的时候如果权限太大会有安全风险。"

**Docker 的好处：**
- 进程隔离，即使 Agent 有问题也不影响主机
- 容器独立运行，关闭对话不影响 Bot
- 资源限制，防止占用过多资源
- 便于部署和迁移

### 6.2 Dockerfile 设计

```dockerfile
FROM python:3.11-slim

# 安装 Node.js（Claude Agent SDK 需要）
RUN curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y nodejs

# 安装 Claude CLI（关键依赖！）
RUN npm install -g @anthropic-ai/claude-code

# 安装 Python 依赖
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 入口脚本（配置 Claude 环境）
COPY entrypoint.sh /entrypoint.sh
CMD ["/entrypoint.sh"]
```

**踩坑记录：** Claude Agent SDK 依赖 Claude CLI，必须安装 `@anthropic-ai/claude-code`！

### 6.3 会话持久化

**需求：**
> "我想要会话能够持久化，30分钟超时，用 /new 命令重置会话"

**实现方案：**
```python
@dataclass
class SessionInfo:
    session_id: str
    user_id: int
    created_at: float
    last_activity: float
    message_count: int

class SessionManager:
    def __init__(self, sessions_file: Path, session_timeout: int = 1800):
        # 从文件加载会话，支持恢复

    def get_session_id(self, user_id: int) -> str | None:
        # 检查超时，返回有效会话 ID
```

**Volume 挂载保证数据不丢失：**
```yaml
volumes:
  - ./users:/app/users      # 用户数据
  - ./config.json:/app/config.json:ro  # 配置文件
```

---

## 7. 问题排查与解决

### 7.1 Markdown 解析错误

**问题：** Bot 发送消息时报错
```
Can't parse entities: can't find end of the entity starting at byte offset 163
```

**原因：** 消息中的 `<user_id>` 被 Telegram 当作 HTML 标签解析

**解决：** 移除 `parse_mode='Markdown'`，改用纯文本

### 7.2 Python 命令找不到

**问题：**
```
nohup: failed to run command 'python': No such file or directory
```

**原因：** Docker 镜像中 Python 命令是 `python3`

**解决：** 使用 `python3` 而不是 `python`

### 7.3 格式化字符串错误

**问题：**
```
Invalid format specifier '.4f if message.total_cost_usd else 0'
```

**原因：** f-string 中的条件表达式语法错误
```python
# 错误
f"cost=${message.total_cost_usd:.4f if message.total_cost_usd else 0}"

# 正确
cost = message.total_cost_usd or 0
f"cost=${cost:.4f}"
```

### 7.4 文件目录不存在

**问题：** 上传文件时报错 `No such file or directory`

**原因：** `mkdir(exist_ok=True)` 不会创建父目录

**解决：** 使用 `mkdir(parents=True, exist_ok=True)`

---

## 8. 功能迭代与优化

### 8.1 文件上传支持

**我的需求：**
> "我上传 PDF 以及一些文档让他帮我总结但是没有得到反应"

**原因分析：** Bot 只处理文本消息，没有处理文件上传

**解决方案：** 添加文档处理器
```python
async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # 下载文件到 uploads/ 目录
    # 构造消息告诉 Agent 用户上传了文件
    # Agent 自动读取并处理

app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
```

### 8.2 长消息处理

**问题：**
> "信息特别长就会分多条消息发送，很乱"

**我的建议：**
> "一旦信息特别长，可以把内容用 txt 文件包裹发送"

**实现：**
```python
MAX_MESSAGE_LENGTH = 2000

async def send_long_message(update, text, caption="📄 回复内容较长，已转为文件"):
    if len(text) <= MAX_MESSAGE_LENGTH:
        await update.message.reply_text(text)
    else:
        file_bytes = BytesIO(text.encode('utf-8'))
        await update.message.reply_document(
            document=file_bytes,
            caption=caption,
            filename="response.txt"
        )
```

### 8.3 Telegram Markdown 兼容

**问题：** Telegram 不支持标准 Markdown 的 `**粗体**` 格式

**解决：** 在系统提示词中明确告诉 Agent：
```
Telegram 消息格式规则（非常重要）:
- 不要使用 **粗体** 或 __粗体__ 格式，Telegram 不支持
- 不要使用 *斜体* 或 _斜体_ 格式
- 可以使用 emoji 来强调重点
- 数字列表和项目符号可以正常使用
```

### 8.4 智能文件组织

**我的需求：**
> "Agent 应该能够自动创建文件夹，把文件放在合适的位置，不要让文件夹太乱"

**系统提示词更新：**
```
文件组织规则（非常重要）:
建议的文件夹结构:
- uploads/ - 用户上传的原始文件
- documents/ - 整理后的文档
- analysis/ - 分析报告和处理结果
- notes/ - 笔记和备忘
- projects/ - 项目相关文件
- data/ - 数据文件

文件组织原则:
1. 根据文件类型和用途自动创建合适的文件夹
2. 分析结果放在 analysis/ 下
3. 创建文件时主动选择合适的目录
```

---

## 9. Skills 系统集成

### 9.1 了解 Skills

**我的问题：**
> "你知道 claude agent 是有 skills 这个功能吗？我想加一个 skills 文件夹"

**AI 的研究结果：**
- Skills 是 Claude Code 的扩展功能
- 放在 `.claude/skills/<skill-name>/SKILL.md`
- 需要配置 `setting_sources=["user", "project"]`
- 需要在 `allowed_tools` 中包含 `"Skill"`

### 9.2 Skills 目录结构

```
.claude/skills/
├── web-research/
│   └── SKILL.md
└── document-analysis/
    └── SKILL.md
```

### 9.3 SKILL.md 格式

```yaml
---
name: skill-name
description: 清晰描述何时使用这个技能（决定 Claude 何时调用）
---

# Skill Name

## 使用场景
- 场景1
- 场景2

## 执行步骤
1. 步骤1
2. 步骤2

## 注意事项
- 注意1
```

### 9.4 踩坑：.dockerignore

**问题：** Skills 没有被复制到容器中

**原因：** `.dockerignore` 中忽略了 `.claude/` 目录

**解决：** 修改 `.dockerignore`，移除对 `.claude/` 的忽略

---

## 10. 经验总结与 AI 协作心得

### 10.1 与 AI 协作的技巧

1. **明确需求，但保持开放**
   - 先说清楚想要什么
   - 但也要听 AI 的建议，可能有更好的方案

2. **迭代式开发**
   - 不要一次要求太多功能
   - 一步步来，每步验证

3. **让 AI 先测试**
   > "你自己先测试一下然后再装到这个 bot 里面吧"

   这个做法非常有效，避免了很多集成问题

4. **问题定位时给 AI 足够信息**
   - 提供完整的错误信息
   - 说明做了什么操作
   - 说明期望的结果

5. **理解 AI 的局限性**
   - AI 可能不知道最新的 SDK 变化
   - 需要让 AI 查阅文档
   - 复杂问题可能需要分步骤解决

### 10.2 这个项目的关键决策

| 决策点 | 选择 | 原因 |
|--------|------|------|
| 编程语言 | Python | 熟悉、生态好 |
| AI 集成方式 | 完全集成（MCP） | 功能最强 |
| 部署方式 | Docker | 安全、隔离 |
| 配置方式 | JSON 文件 | 简单直观 |
| 会话管理 | 文件持久化 | 简单可靠 |

### 10.3 项目最终架构

```
telegram-bot/
├── main.py                 # 入口
├── config.json             # 配置
├── requirements.txt        # Python 依赖
├── Dockerfile              # Docker 配置
├── docker-compose.yml      # Docker Compose
├── entrypoint.sh           # 启动脚本
├── .dockerignore           # Docker 忽略
├── bot/                    # Bot 模块
│   ├── handlers.py         # 命令处理
│   ├── agent/              # Agent 模块
│   ├── user/               # 用户管理
│   └── session/            # 会话管理
├── .claude/skills/         # Skills
├── users/                  # 用户数据（持久化）
└── docs/                   # 文档
```

### 10.4 后续优化方向

1. **更多 Skills** - 添加更多实用技能
2. **多语言支持** - 支持英文等其他语言
3. **更好的错误处理** - 更友好的错误提示
4. **用户界面** - 添加 Web 管理界面
5. **监控和日志** - 更完善的运行监控

---

## 附录

### A. 常用命令

```bash
# 查看容器日志
docker compose logs -f

# 重启服务
docker compose restart

# 重建并启动
docker compose up -d --build

# 查看用户数据
ls -la users/

# 进入容器调试
docker exec -it telegram-file-bot bash
```

### B. 项目链接

- 作者推特：https://x.com/yrzhe_top
- Claude Agent SDK 文档：https://docs.anthropic.com

---

*这篇文档记录了一个完整的 AI 协作开发过程，希望对你有帮助！*
