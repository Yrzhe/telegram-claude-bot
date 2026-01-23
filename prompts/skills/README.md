# Skills System

Skills are specialized modules that provide expert knowledge and workflows.
This directory contains skill description templates that are dynamically loaded.

## How Skills Work

1. Built-in skills are loaded from `.claude/skills/` directory
2. User custom skills are loaded from `users/{user_id}/skills/`
3. Skill descriptions are injected into the system prompt at runtime
4. Use the `Skill` tool to load full skill instructions when needed

## Skill Types

### Official Skills (Built-in)
Located in `.claude/skills/`, available to all users.

### User Skills (Custom)
Uploaded by users, stored in their personal skills directory.

## Adding New Skills

1. Create a new directory in `.claude/skills/` with your skill name
2. Create a `SKILL.md` file with YAML frontmatter:
   ```yaml
   ---
   name: skill-name
   description: Brief description of what the skill does
   triggers:
     - when to use this skill
     - trigger keywords
   ---
   ```
3. Add the skill instructions in the markdown body
4. The skill will be automatically available to the agent

## Skill Loading

Skills are loaded dynamically when the agent is initialized.
The skill metadata (name, description, triggers) is included in the system prompt.
Full skill content is loaded when the agent invokes the `Skill` tool.
