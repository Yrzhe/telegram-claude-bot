# Agent 定时任务控制 & 任务结束强制发送文件

日期: 2026-01-11

## 需求概述

1. **Agent 定时任务完全控制**：Agent 可通过 MCP 工具创建、修改、删除定时任务
2. **任务结束强制发送文件**：每次任务完成时自动检测并发送新生成的文件

## 设计详情

### 一、Agent 定时任务控制

#### 1.1 新增 MCP 工具

| 工具名 | 参数 | 功能 |
|--------|------|------|
| `schedule_list` | 无 | 列出用户所有定时任务 |
| `schedule_get` | `task_id` | 获取任务详情（含 prompt） |
| `schedule_create` | `task_id`, `name`, `time`, `prompt`, `enabled?` | 创建新任务 |
| `schedule_update` | `task_id`, `name?`, `time?`, `prompt?`, `enabled?` | 更新任务属性 |
| `schedule_delete` | `task_id` | 删除任务 |

#### 1.2 格式校验规则

- **task_id**: 正则 `^[a-zA-Z0-9_]{1,32}$`，不允许重复
- **time**: 格式 `HH:MM`，范围 00:00-23:59
- **必填字段**: create 时 task_id, name, time, prompt 必填
- **update**: 至少提供一个可选参数

#### 1.3 操作日志

存储位置: `users/{user_id}/data/schedules/operation_log.jsonl`

日志格式:
```json
{"timestamp": "ISO8601", "action": "create|update|delete", "task_id": "xxx", "details": {...}}
```

删除操作保存完整快照（包括 prompt），便于恢复。

### 二、任务结束强制发送文件

#### 2.1 FileTracker 类

```python
class FileTracker:
    """追踪任务期间新建/修改的文件"""

    def start(self):
        """任务开始时调用，记录当前文件状态"""

    def get_new_files(self) -> list[Path]:
        """任务结束时调用，返回新建/修改的文件列表"""
```

#### 2.2 文件过滤规则

**排除的扩展名:**
- `.tmp`, `.log`, `.pyc`, `.pyo`, `.swp`, `.swo`

**排除的目录:**
- `__pycache__/`, `.git/`, `node_modules/`, `.venv/`, `.cache/`

**排除的文件名模式:**
- 以 `.` 开头的隐藏文件
- 以 `~` 开头的临时文件

#### 2.3 发送策略

- **≤5 个文件**: 逐个发送
- **>5 个文件**: 打包成 zip 发送，发送后立即删除 zip（不占用用户空间）

#### 2.4 适用范围

- 用户消息处理完成时
- 定时任务执行完成时

### 三、文件结构变更

```
bot/
├── agent/
│   ├── client.py         # 修改：集成 FileTracker
│   └── tools.py          # 修改：新增 5 个定时任务工具
├── schedule/
│   └── manager.py        # 修改：添加日志记录方法
└── file_tracker.py       # 新增：文件变更追踪器
```

### 四、集成点

1. **tools.py**: 通过 `set_tool_config()` 注入 `schedule_manager`
2. **client.py**: 在 `process_message()` 中集成 FileTracker
3. **handlers.py**: 定时任务执行时也使用 FileTracker

### 五、allowed_tools 更新

```python
allowed_tools = [
    # 现有工具...
    "mcp__telegram__schedule_list",
    "mcp__telegram__schedule_get",
    "mcp__telegram__schedule_create",
    "mcp__telegram__schedule_update",
    "mcp__telegram__schedule_delete",
]
```

## 实现步骤

1. 创建 `bot/file_tracker.py` - 文件变更追踪器
2. 修改 `bot/schedule/manager.py` - 添加操作日志功能
3. 修改 `bot/agent/tools.py` - 添加 5 个定时任务工具
4. 修改 `bot/agent/client.py` - 集成 FileTracker 和新工具
5. 修改 `bot/handlers.py` - 定时任务执行时集成 FileTracker
6. 更新 `bot/i18n.py` - 添加新的翻译字符串
7. 测试验证
