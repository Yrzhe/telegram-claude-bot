# 定时任务扩展设计

## 概述

扩展现有的每日定时任务系统，支持更多周期类型和执行次数限制。

## 新增功能

1. **周期类型扩展**
   - `daily` - 每天（现有）
   - `weekly` - 每周指定星期
   - `monthly` - 每月指定日期
   - `interval` - 间隔执行（每 N 分钟/小时）
   - `once` - 一次性任务

2. **执行次数限制**
   - 可设置最大执行次数
   - 达到上限后自动禁用（保留配置）
   - 用户可手动重新启用或删除

## 数据模型

```python
@dataclass
class ScheduledTask:
    task_id: str
    name: str
    hour: int           # 0-23
    minute: int         # 0-59
    enabled: bool = True
    last_run: Optional[str] = None
    created_at: Optional[str] = None

    # 新增字段
    schedule_type: str = "daily"  # daily, weekly, monthly, interval, once
    weekdays: Optional[List[int]] = None  # 0=周一, 6=周日
    month_day: Optional[int] = None  # 1-31
    interval_minutes: Optional[int] = None
    run_date: Optional[str] = None  # YYYY-MM-DD (for once)
    max_runs: Optional[int] = None  # None = 无限制
    run_count: int = 0
```

## 命令格式

| 类型 | 格式 | 示例 |
|------|------|------|
| 每天 | `daily HH:MM` | `/schedule add task1 daily 09:00 每日报告` |
| 每周 | `weekly HH:MM 星期` | `/schedule add task2 weekly 09:00 mon,wed,fri 周报` |
| 每月 | `monthly HH:MM 日期` | `/schedule add task3 monthly 10:00 1 月初汇总` |
| 间隔 | `interval 时长` | `/schedule add task4 interval 2h 定时检查` |
| 一次性 | `once 日期 HH:MM` | `/schedule add task5 once 2025-01-20 14:00 提醒` |

执行次数限制：`--max N`

```
/schedule add task6 daily 09:00 --max 5 测试任务
```

## 调度实现

| 类型 | Telegram API | 说明 |
|------|-------------|------|
| daily | `run_daily()` | 现有逻辑 |
| weekly | `run_daily()` + 回调检查 | 每天触发，回调中判断星期 |
| monthly | `run_daily()` + 回调检查 | 每天触发，回调中判断日期 |
| interval | `run_repeating()` | 间隔重复执行 |
| once | `run_once()` | 一次性执行 |

## 需要修改的文件

- `bot/schedule/manager.py` - 数据模型和调度逻辑
- `bot/handlers.py` - 命令解析和显示
- `bot/agent/tools.py` - Agent 工具更新
- `bot/i18n/` - 多语言文本
- `CHANGELOG.md` - 更新日志
