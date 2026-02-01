# Task Understanding - Parsing Complex User Requests

## Time-Bound Task Patterns

When users request tasks with time qualifiers, understand the TRUE intent:

### Pattern 1: "时间 + 提醒我 + 动作"

Examples:
- "晚上提醒我调研XX"
- "明天帮我查一下XX"
- "下午提醒我分析XX"

**Correct interpretation**: Create a SCHEDULED TASK that:
1. Executes the action (研究/调研/查/分析) at the specified time
2. Sends results to user when done

**Wrong interpretation**:
- ❌ Execute NOW + set a separate "提醒" reminder
- ❌ Split into two independent tasks

**Implementation**:
```
schedule_create(
    task_id="research_xxx",
    name="调研XXX",
    schedule_type="once",
    time="20:00",  # Evening time
    run_date="2024-01-15",  # Today or tomorrow
    prompt="调研XXX，包含：1. 基本情况 2. 业务分析 3. 关键数据。完成后发送详细报告给用户。"
)
```

### Pattern 2: "先给我XX，时间再提醒我"

Examples:
- "你可以先给一些资料给我，晚上提醒我深入研究"
- "先简单说说，明天详细分析"

**Correct interpretation**: This IS two separate tasks:
1. NOW: Provide preliminary information (quick response or delegate)
2. LATER: Schedule a more detailed task

### Pattern 3: Ambiguous Time Instructions

When unclear, **ASK the user** before acting:

Example: "晚上提醒我调研一下中兴通讯吧，你可以先给一些资料给我"

This is ambiguous! User might mean:
- A) 现在给资料 + 晚上深入调研
- B) 晚上调研并提醒（先给资料只是顺便）

**Ask for clarification**:
"我有两种理解：
1. 现在先给你基本资料，晚上我再进行深度调研并发给你
2. 晚上统一调研，现在先不用管

你希望哪种方式？"

---

## Task Failure Recovery

When a scheduled task creation fails:

### DO NOT give up immediately!

1. **Analyze the error** - Is it a parameter issue? Missing time format? Invalid task_id?

2. **Fix and retry** - If it's a fixable issue:
   - Wrong time format → Fix to HH:MM
   - Invalid task_id → Generate a valid one
   - Missing required field → Fill it in

3. **Offer alternatives** if feature unavailable:
   - "定时任务暂时无法创建，我可以现在就帮你完成这个调研，你自己设个闹钟晚上看结果？"
   - "或者我把调研结果保存到文件里，你晚上有空再看？"

4. **Never leave tasks half-done**:
   - If you committed to doing TWO things, complete BOTH or explain why both can't be done
   - Don't just do one and silently drop the other

---

## Multi-Step Task Handling

When a user request involves multiple steps:

### Identify Dependencies

- **Independent steps**: Can run in parallel (delegate both)
- **Sequential steps**: One depends on the other (chain them)

### Example: "调研XX并发给我，晚上提醒我看"

Steps:
1. Research XX (can start now)
2. Send results (after research completes)
3. Remind user tonight (can be scheduled now)

Approach:
```
1. delegate_and_review: Start research task
2. schedule_create: Create reminder for tonight
3. Message user: "正在调研中，完成后会发给你。同时设了晚上8点的提醒。"
```

### Never Drop Tasks Silently

If step 2 fails after step 1 succeeds:
- Tell user what succeeded and what failed
- Offer to retry the failed step
- Don't just report partial success as if everything is fine

---

## Common Misunderstandings to Avoid

| User Says | Wrong Understanding | Correct Understanding |
|-----------|--------------------|-----------------------|
| "晚上提醒我调研X" | Now: research / Later: remind | Schedule: research X tonight, then notify |
| "明天帮我查X" | Now: search X | Schedule: search X tomorrow |
| "先给点资料，晚上详细" | Only give materials now | Give materials now + schedule detailed task |
| "下班后提醒我" | Set reminder only | Schedule task for after work |

---

## When to Ask vs When to Assume

**Ask when**:
- Time is vague ("晚上" - what time exactly?)
- Intent is ambiguous (see Pattern 3 above)
- User request has conflicting instructions

**Assume when**:
- Time is specific ("晚上8点")
- Intent is clear from context
- User has shown preference before (check preferences.txt)

Default time mappings if not asking:
- "早上" → 08:00
- "上午" → 10:00
- "中午" → 12:00
- "下午" → 15:00
- "晚上" → 20:00
- "深夜" → 23:00
