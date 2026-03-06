"""Cleanup Agent API routes."""

import asyncio
import json
import logging
import shutil
import uuid
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from fastapi import APIRouter, HTTPException, status, Depends
from pydantic import BaseModel

from ..dependencies import get_current_user_id, get_working_directory, get_user_manager, get_api_config
from ..websocket import ws_manager

logger = logging.getLogger(__name__)

router = APIRouter()

# --- Pydantic Models ---

class CleanupAction(BaseModel):
    action: str  # delete | archive | move
    path: str
    target: Optional[str] = None
    reason: str
    size_bytes: int = 0
    item_count: int = 1


class CleanupPlan(BaseModel):
    plan_id: str
    actions: List[CleanupAction]
    total_size_bytes: int = 0
    total_items: int = 0
    summary: str = ""
    created_at: str = ""
    error: Optional[str] = None


class CleanupResult(BaseModel):
    success_count: int = 0
    fail_count: int = 0
    freed_bytes: int = 0
    errors: List[str] = []


class CleanupStatusResponse(BaseModel):
    status: str  # idle | planning | ready | executing | completed | failed
    plan: Optional[CleanupPlan] = None
    result: Optional[CleanupResult] = None
    error: Optional[str] = None


class CleanupRulesResponse(BaseModel):
    content: str
    modified_at: Optional[str] = None


class CleanupPlanRequest(BaseModel):
    feedback: Optional[str] = None


class CleanupExecuteRequest(BaseModel):
    plan_id: str


class CleanupRulesUpdateRequest(BaseModel):
    content: str


# --- In-Memory Session Store ---

_cleanup_sessions: Dict[int, dict] = {}

DEFAULT_RULES = """# Cleanup Rules

## Protected Directories (NEVER delete)
- completed_tasks/
- running_tasks/
- schedules/
- custom_commands/
- .temp/
- .voice_temp/
- uploads/

## Protected Files (NEVER delete)
- memories.json
- topics.json
- preferences.txt
- .context_summary.txt
- .cleanup_rules.md

## Cleanup Preferences
- Delete files in temp/ older than 7 days
- Archive directories not modified in 30 days
- Delete empty directories
- Delete duplicate files (keep newest)

## Custom Rules
<!-- Add your own rules below -->
"""

# System-protected paths (hardcoded, cannot be overridden)
PROTECTED_DIRS = {
    "completed_tasks", "running_tasks", "schedules", "custom_commands",
    ".temp", ".voice_temp"
}
PROTECTED_FILES = {
    "memories.json", "topics.json", "preferences.txt",
    ".context_summary.txt", ".cleanup_rules.md"
}


def _get_session(user_id: int) -> dict:
    if user_id not in _cleanup_sessions:
        _cleanup_sessions[user_id] = {
            "status": "idle",
            "plan": None,
            "result": None,
            "error": None
        }
    return _cleanup_sessions[user_id]


def _get_rules_path(working_dir: str) -> Path:
    return Path(working_dir) / "data" / ".cleanup_rules.md"


def _is_protected_path(rel_path: str) -> bool:
    """Check if a relative path is protected."""
    parts = Path(rel_path).parts
    if not parts:
        return True
    # Check top-level directory
    if parts[0] in PROTECTED_DIRS:
        return True
    # Check exact file match at top level
    if len(parts) == 1 and parts[0] in PROTECTED_FILES:
        return True
    # Check filename in any directory
    if Path(rel_path).name in PROTECTED_FILES:
        return True
    return False


def _validate_path(rel_path: str, data_dir: Path) -> Optional[Path]:
    """Validate and resolve a relative path within data_dir. Returns None if invalid."""
    try:
        resolved = (data_dir / rel_path).resolve()
        # Ensure it's within data_dir
        if not str(resolved).startswith(str(data_dir.resolve())):
            return None
        return resolved
    except (ValueError, OSError):
        return None


# --- Endpoints ---

@router.get("/rules", response_model=CleanupRulesResponse)
async def get_rules(
    user_id: int = Depends(get_current_user_id),
    working_dir: str = Depends(get_working_directory)
):
    """Get the cleanup rules file content."""
    rules_path = _get_rules_path(working_dir)
    if rules_path.exists():
        content = rules_path.read_text(encoding="utf-8")
        mtime = datetime.fromtimestamp(rules_path.stat().st_mtime).isoformat()
        return CleanupRulesResponse(content=content, modified_at=mtime)
    return CleanupRulesResponse(content=DEFAULT_RULES)


@router.put("/rules")
async def update_rules(
    body: CleanupRulesUpdateRequest,
    user_id: int = Depends(get_current_user_id),
    working_dir: str = Depends(get_working_directory)
):
    """Save the cleanup rules file."""
    rules_path = _get_rules_path(working_dir)
    rules_path.parent.mkdir(parents=True, exist_ok=True)
    rules_path.write_text(body.content, encoding="utf-8")
    return {"success": True}


@router.get("/status", response_model=CleanupStatusResponse)
async def get_status(
    user_id: int = Depends(get_current_user_id)
):
    """Get current cleanup session status."""
    session = _get_session(user_id)
    return CleanupStatusResponse(
        status=session["status"],
        plan=session.get("plan"),
        result=session.get("result"),
        error=session.get("error")
    )


@router.post("/plan", response_model=CleanupStatusResponse)
async def generate_plan(
    body: CleanupPlanRequest = CleanupPlanRequest(),
    user_id: int = Depends(get_current_user_id),
    working_dir: str = Depends(get_working_directory),
    api_config: dict = Depends(get_api_config)
):
    """Generate a cleanup plan using a sub-agent."""
    session = _get_session(user_id)

    if session["status"] == "planning":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A cleanup plan is already being generated"
        )

    # Set status to planning
    session["status"] = "planning"
    session["plan"] = None
    session["result"] = None
    session["error"] = None

    # Notify frontend via WebSocket
    await ws_manager.send_to_user(user_id, {
        "type": "cleanup_update",
        "data": {"status": "planning"}
    })

    # Run planning in background
    asyncio.create_task(_run_planning(user_id, working_dir, api_config, body.feedback))

    return CleanupStatusResponse(status="planning")


async def _run_planning(user_id: int, working_dir: str, api_config: dict, feedback: Optional[str]):
    """Run the cleanup planning sub-agent in background."""
    session = _get_session(user_id)
    data_dir = Path(working_dir) / "data"

    try:
        from bot.agent import create_sub_agent

        # Build env vars
        env_vars = {}
        if api_config.get("api_key"):
            env_vars["ANTHROPIC_API_KEY"] = api_config["api_key"]
        if api_config.get("base_url"):
            env_vars["ANTHROPIC_BASE_URL"] = api_config["base_url"]

        sub_agent = create_sub_agent(
            user_id=user_id,
            working_directory=str(data_dir),
            env_vars=env_vars,
            model=api_config.get("model"),
            max_turns=10
        )

        # Progress callback: stream agent steps to frontend via WebSocket
        _progress_logs: list[str] = []

        async def on_progress(message: str):
            _progress_logs.append(message)
            await ws_manager.send_to_user(user_id, {
                "type": "cleanup_progress",
                "data": {"message": message, "logs": _progress_logs}
            })

        # Read current rules
        rules_path = _get_rules_path(working_dir)
        if rules_path.exists():
            rules_content = rules_path.read_text(encoding="utf-8")
        else:
            rules_content = DEFAULT_RULES

        feedback_section = ""
        if feedback:
            feedback_section = f"""
USER FEEDBACK ON PREVIOUS PLAN:
{feedback}

Adjust your plan based on this feedback.
"""

        prompt = f"""You are a file cleanup planning agent. Scan the current working directory and propose a cleanup plan.

STEPS:
1. Read the cleanup rules below to understand protected paths and user preferences
2. Use Glob("**/*") to scan the full directory tree
3. Identify files/directories that can be safely cleaned up based on the rules
4. Output ONLY valid JSON (no markdown fences, no explanation) with this structure:

{{"actions": [{{"action": "delete", "path": "relative/path", "reason": "Explanation", "size_bytes": 1024, "item_count": 1}}, {{"action": "archive", "path": "relative/dir/", "target": "archives/dir.zip", "reason": "Explanation", "size_bytes": 5242880, "item_count": 15}}], "summary": "Found N items (X MB) to clean up"}}

RULES:
- action must be one of: delete, archive, move
- path must be RELATIVE to the working directory
- CRITICAL: Each path must be an EXACT file or directory name. NEVER use glob patterns or wildcards like *.png or nb_*.txt. List each file individually.
- For archive actions, target is where to put the zip file
- For move actions, target is the destination path
- size_bytes should be the actual file/directory size
- item_count is 1 for files, or the number of files in a directory
- To delete an entire directory and all its contents, just specify the directory path (e.g. "analysis/") — no need to list individual files inside it

PROTECTED PATHS (NEVER include in actions):
completed_tasks/, running_tasks/, schedules/, custom_commands/, .temp/, .voice_temp/,
memories.json, topics.json, preferences.txt, .context_summary.txt, .cleanup_rules.md

USER CLEANUP RULES:
{rules_content}
{feedback_section}
If there is nothing to clean up, output: {{"actions": [], "summary": "No files need cleanup"}}

IMPORTANT: Output ONLY the JSON object, nothing else."""

        response = await sub_agent.process_message(prompt, progress_callback=on_progress)

        # Parse JSON from response
        response_text = (response.text or "").strip()
        # Try to extract JSON from the response
        plan_data = _parse_plan_json(response_text)

        plan_id = str(uuid.uuid4())[:8]
        actions = []
        total_size = 0
        total_items = 0

        for a in plan_data.get("actions", []):
            # Skip protected paths
            if _is_protected_path(a.get("path", "")):
                continue
            action = CleanupAction(
                action=a.get("action", "delete"),
                path=a.get("path", ""),
                target=a.get("target"),
                reason=a.get("reason", ""),
                size_bytes=a.get("size_bytes", 0),
                item_count=a.get("item_count", 1)
            )
            actions.append(action)
            total_size += action.size_bytes
            total_items += action.item_count

        plan = CleanupPlan(
            plan_id=plan_id,
            actions=actions,
            total_size_bytes=total_size,
            total_items=total_items,
            summary=plan_data.get("summary", f"Found {len(actions)} actions"),
            created_at=datetime.now().isoformat()
        )

        session["status"] = "ready"
        session["plan"] = plan

        await ws_manager.send_to_user(user_id, {
            "type": "cleanup_update",
            "data": {
                "status": "ready",
                "plan": plan.model_dump()
            }
        })

    except Exception as e:
        logger.error(f"Cleanup planning failed for user {user_id}: {e}")
        session["status"] = "failed"
        session["error"] = str(e)

        await ws_manager.send_to_user(user_id, {
            "type": "cleanup_update",
            "data": {
                "status": "failed",
                "error": str(e)
            }
        })


def _parse_plan_json(text: str) -> dict:
    """Extract and parse JSON from agent response text."""
    # Try direct parse
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Try to find JSON block in markdown fences
    import re
    json_match = re.search(r'```(?:json)?\s*\n?(.*?)\n?```', text, re.DOTALL)
    if json_match:
        try:
            return json.loads(json_match.group(1))
        except json.JSONDecodeError:
            pass

    # Try to find JSON object in text
    brace_start = text.find('{')
    if brace_start >= 0:
        # Find matching closing brace
        depth = 0
        for i in range(brace_start, len(text)):
            if text[i] == '{':
                depth += 1
            elif text[i] == '}':
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(text[brace_start:i+1])
                    except json.JSONDecodeError:
                        break

    raise ValueError(f"Could not parse JSON from agent response: {text[:200]}")


@router.post("/execute", response_model=CleanupStatusResponse)
async def execute_plan(
    body: CleanupExecuteRequest,
    user_id: int = Depends(get_current_user_id),
    working_dir: str = Depends(get_working_directory)
):
    """Execute an approved cleanup plan."""
    session = _get_session(user_id)

    if session["status"] != "ready":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No plan ready to execute"
        )

    plan = session.get("plan")
    if not plan or plan.plan_id != body.plan_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Plan ID mismatch"
        )

    session["status"] = "executing"
    await ws_manager.send_to_user(user_id, {
        "type": "cleanup_update",
        "data": {"status": "executing"}
    })

    # Execute synchronously (file ops are fast)
    data_dir = Path(working_dir) / "data"
    result = _execute_plan(plan, data_dir)

    session["status"] = "completed"
    session["result"] = result

    await ws_manager.send_to_user(user_id, {
        "type": "cleanup_update",
        "data": {
            "status": "completed",
            "result": result.model_dump()
        }
    })

    return CleanupStatusResponse(
        status="completed",
        plan=plan,
        result=result
    )


def _execute_plan(plan: CleanupPlan, data_dir: Path) -> CleanupResult:
    """Execute cleanup actions using direct Python file operations."""
    success_count = 0
    fail_count = 0
    freed_bytes = 0
    errors = []

    for action in plan.actions:
        try:
            # Safety checks
            if _is_protected_path(action.path):
                errors.append(f"Skipped protected path: {action.path}")
                fail_count += 1
                continue

            # Expand glob patterns if the path contains wildcards
            if any(c in action.path for c in ('*', '?', '[')):
                expanded = sorted(data_dir.glob(action.path))
                # Filter out protected paths
                expanded = [
                    p for p in expanded
                    if not _is_protected_path(str(p.relative_to(data_dir)))
                ]
                if not expanded:
                    errors.append(f"No files matched pattern: {action.path}")
                    fail_count += 1
                    continue
                # Execute action on each matched path
                for matched_path in expanded:
                    rel = str(matched_path.relative_to(data_dir))
                    try:
                        if not matched_path.exists():
                            continue
                        if matched_path.is_file():
                            sz = matched_path.stat().st_size
                            matched_path.unlink()
                            freed_bytes += sz
                        elif matched_path.is_dir():
                            sz = sum(f.stat().st_size for f in matched_path.rglob("*") if f.is_file())
                            shutil.rmtree(str(matched_path))
                            freed_bytes += sz
                        success_count += 1
                    except Exception as e:
                        errors.append(f"Error on {rel}: {str(e)}")
                        fail_count += 1
                continue

            resolved = _validate_path(action.path, data_dir)
            if not resolved:
                errors.append(f"Invalid path: {action.path}")
                fail_count += 1
                continue

            if not resolved.exists():
                errors.append(f"Path not found: {action.path}")
                fail_count += 1
                continue

            # Get actual size before operation
            if resolved.is_file():
                actual_size = resolved.stat().st_size
            elif resolved.is_dir():
                actual_size = sum(f.stat().st_size for f in resolved.rglob("*") if f.is_file())
            else:
                actual_size = 0

            if action.action == "delete":
                if resolved.is_file():
                    resolved.unlink()
                elif resolved.is_dir():
                    shutil.rmtree(str(resolved))
                freed_bytes += actual_size
                success_count += 1

            elif action.action == "archive":
                # Create archive directory
                archives_dir = data_dir / "archives"
                archives_dir.mkdir(parents=True, exist_ok=True)

                target_name = action.target or f"archives/{Path(action.path).stem}.zip"
                target_path = _validate_path(target_name, data_dir)
                if not target_path:
                    errors.append(f"Invalid archive target: {target_name}")
                    fail_count += 1
                    continue

                target_path.parent.mkdir(parents=True, exist_ok=True)

                # Create zip
                with zipfile.ZipFile(str(target_path), 'w', zipfile.ZIP_DEFLATED) as zf:
                    if resolved.is_file():
                        zf.write(str(resolved), resolved.name)
                    elif resolved.is_dir():
                        for file in resolved.rglob("*"):
                            if file.is_file():
                                zf.write(str(file), str(file.relative_to(resolved.parent)))

                # Delete original after archiving
                if resolved.is_file():
                    resolved.unlink()
                elif resolved.is_dir():
                    shutil.rmtree(str(resolved))

                archive_size = target_path.stat().st_size
                freed_bytes += max(0, actual_size - archive_size)
                success_count += 1

            elif action.action == "move":
                if not action.target:
                    errors.append(f"No target for move: {action.path}")
                    fail_count += 1
                    continue

                target_path = _validate_path(action.target, data_dir)
                if not target_path:
                    errors.append(f"Invalid move target: {action.target}")
                    fail_count += 1
                    continue

                target_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(resolved), str(target_path))
                success_count += 1

            else:
                errors.append(f"Unknown action: {action.action}")
                fail_count += 1

        except Exception as e:
            errors.append(f"Error on {action.path}: {str(e)}")
            fail_count += 1
            logger.error(f"Cleanup action failed for {action.path}: {e}")

    return CleanupResult(
        success_count=success_count,
        fail_count=fail_count,
        freed_bytes=freed_bytes,
        errors=errors
    )


@router.post("/cancel")
async def cancel_cleanup(
    user_id: int = Depends(get_current_user_id)
):
    """Reset cleanup session to idle."""
    session = _get_session(user_id)
    session["status"] = "idle"
    session["plan"] = None
    session["result"] = None
    session["error"] = None

    await ws_manager.send_to_user(user_id, {
        "type": "cleanup_update",
        "data": {"status": "idle"}
    })

    return {"success": True}
