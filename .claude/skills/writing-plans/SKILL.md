---
name: writing-plans
description: Use when you have a spec or requirements for a multi-step task, before starting work
---

# Writing Plans

## Overview

Write comprehensive step-by-step plans that break complex tasks into small, actionable steps. Each step should be clear enough to execute without additional context.

**Announce at start:** "I'm using the writing-plans skill to create the implementation plan."

**Save plans to:** `plans/<date>-<topic>.md` in user's workspace

## Bite-Sized Task Granularity

**Each step is one small action:**
- "Search for relevant information about X"
- "Create the outline document"
- "Write the introduction section"
- "Review and refine the content"
- "Send the result to user"

**Bad examples (too vague):**
- "Do the research" - too broad
- "Write the document" - needs breakdown
- "Handle the data" - unclear

## Plan Document Header

**Every plan MUST start with this header:**

```markdown
# [Task Name] Plan

**Goal:** [One sentence describing what this accomplishes]

**Approach:** [2-3 sentences about how we'll do it]

**Output:** [What will be delivered]

---
```

## Task Structure

```markdown
### Task N: [Component Name]

**Files involved:**
- Create: `exact/path/to/file.ext`
- Read: `exact/path/to/source.ext`
- Output: `exact/path/to/result.ext`

**Step 1: [Action]**
[Clear description of what to do]

**Step 2: [Action]**
[Clear description of what to do]

**Step 3: Verify**
[How to check this task is complete]
```

## Remember
- Exact file paths always
- Clear descriptions (not "do the thing")
- Include verification steps
- Break large tasks into smaller ones
- Keep it simple - don't over-complicate

## Execution Handoff

After saving the plan, offer execution choice:

**"Plan complete and saved to `plans/<filename>.md`. Ready to start execution?"**

If user confirms:
- Use executing-plans skill to work through tasks
- Execute tasks one by one
- Report progress after each task
