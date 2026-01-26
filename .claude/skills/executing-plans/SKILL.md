---
name: executing-plans
description: Use when you have a written plan to execute, working through tasks with progress updates
---

# Executing Plans

## Overview

Load plan, review it, execute tasks one by one, report progress to user.

**Core principle:** Execute tasks systematically, report progress, get feedback.

**Announce at start:** "I'm using the executing-plans skill to implement this plan."

## The Process

### Step 1: Load and Review Plan
1. Read the plan file
2. Review it - identify any questions or concerns
3. If concerns: Raise them with user before starting
4. If no concerns: Proceed to execution

### Step 2: Execute Tasks
For each task:
1. Announce: "Starting Task N: [name]"
2. Follow each step as written in the plan
3. Verify completion as specified
4. Report: "Task N complete. [brief result]"

### Step 3: Progress Report
After each task:
- Show what was done
- Show any outputs or results
- Ask: "Continue to next task?"

### Step 4: Handle Issues
If blocked:
- Stop immediately
- Explain the issue
- Ask user for guidance
- Don't guess or work around problems

### Step 5: Complete
When all tasks done:
- Summarize what was accomplished
- List all outputs/files created
- Send relevant files to user

## When to Stop and Ask for Help

**STOP executing immediately when:**
- Plan step is unclear or ambiguous
- Something unexpected happens
- Required information is missing
- You're unsure how to proceed

**Ask for clarification rather than guessing.**

## Remember
- Follow plan steps exactly
- Report progress after each task
- Stop when blocked, don't guess
- Keep user informed throughout
- Deliver results when complete
