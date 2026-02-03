"""Sub Agents API routes."""

import logging
from typing import Optional, List, Dict, Any
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, HTTPException, status, Depends, Query
from pydantic import BaseModel

from ..dependencies import (
    get_current_user_id,
    get_task_manager_for_user,
    get_working_directory
)

logger = logging.getLogger(__name__)

router = APIRouter()


class RunningAgent(BaseModel):
    """Running Sub Agent information."""
    task_id: str
    description: str
    started_at: str
    elapsed_seconds: int
    needs_review: bool = False
    retry_count: int = 0
    max_retries: int = 0


class SubAgentStatus(BaseModel):
    """Sub Agent pool status."""
    max_agents: int
    active_count: int
    available_slots: int
    running_tasks: List[RunningAgent]


class CompletedAgent(BaseModel):
    """Completed Sub Agent information."""
    task_id: str
    description: str
    status: str
    created_at: str
    duration_seconds: Optional[int] = None
    result_preview: Optional[str] = None


class SubAgentHistoryResponse(BaseModel):
    """Sub Agent history response."""
    completed: List[CompletedAgent]
    total_count: int


class TaskDocumentResponse(BaseModel):
    """Task document content response."""
    task_id: str
    content: str
    modified_at: str


@router.get("/status", response_model=SubAgentStatus)
async def get_subagent_status(
    user_id: int = Depends(get_current_user_id),
    task_manager = Depends(get_task_manager_for_user)
):
    """
    Get Sub Agent pool status.
    """
    max_agents = task_manager.MAX_SUB_AGENTS
    active_count = task_manager.active_task_count

    # Get running tasks details
    running_tasks = []
    now = datetime.now()

    for task in task_manager._tasks.values():
        if task.status.value in ("pending", "running"):
            elapsed = (now - task.created_at).total_seconds()
            running_tasks.append(RunningAgent(
                task_id=task.task_id,
                description=task.description,
                started_at=task.created_at.strftime('%Y-%m-%d %H:%M:%S'),
                elapsed_seconds=int(elapsed),
                needs_review=task.needs_review,
                retry_count=task.retry_count,
                max_retries=task.max_retries
            ))

    # Sort by start time (newest first)
    running_tasks.sort(key=lambda t: t.started_at, reverse=True)

    return SubAgentStatus(
        max_agents=max_agents,
        active_count=active_count,
        available_slots=max_agents - active_count,
        running_tasks=running_tasks
    )


@router.get("/running", response_model=List[RunningAgent])
async def get_running_agents(
    user_id: int = Depends(get_current_user_id),
    task_manager = Depends(get_task_manager_for_user)
):
    """
    Get list of currently running Sub Agents.
    """
    running = []
    now = datetime.now()

    for task in task_manager._tasks.values():
        if task.status.value in ("pending", "running"):
            elapsed = (now - task.created_at).total_seconds()
            running.append(RunningAgent(
                task_id=task.task_id,
                description=task.description,
                started_at=task.created_at.strftime('%Y-%m-%d %H:%M:%S'),
                elapsed_seconds=int(elapsed),
                needs_review=task.needs_review,
                retry_count=task.retry_count,
                max_retries=task.max_retries
            ))

    running.sort(key=lambda t: t.elapsed_seconds, reverse=True)
    return running


@router.get("/history", response_model=SubAgentHistoryResponse)
async def get_subagent_history(
    limit: int = Query(20, ge=1, le=100),
    user_id: int = Depends(get_current_user_id),
    task_manager = Depends(get_task_manager_for_user)
):
    """
    Get completed Sub Agent history.
    """
    completed = []

    for task in task_manager._tasks.values():
        if task.status.value in ("completed", "failed", "cancelled"):
            # Calculate duration if possible
            duration = None
            # Task doesn't store completion time, estimate from now
            # In production, you'd want to store the completion time

            result_preview = None
            if task.result:
                result_preview = task.result[:200] + "..." if len(task.result) > 200 else task.result

            completed.append(CompletedAgent(
                task_id=task.task_id,
                description=task.description,
                status=task.status.value,
                created_at=task.created_at.strftime('%Y-%m-%d %H:%M:%S'),
                duration_seconds=duration,
                result_preview=result_preview
            ))

    # Sort by created time (newest first)
    completed.sort(key=lambda t: t.created_at, reverse=True)

    return SubAgentHistoryResponse(
        completed=completed[:limit],
        total_count=len(completed)
    )


@router.get("/{task_id}/document", response_model=TaskDocumentResponse)
async def get_task_document(
    task_id: str,
    user_id: int = Depends(get_current_user_id),
    working_dir: str = Depends(get_working_directory)
):
    """
    Get the content of a task document.
    """
    base_path = Path(working_dir) / "data"

    # Check running_tasks first
    running_doc = base_path / "running_tasks" / f"{task_id}.md"
    completed_doc = base_path / "completed_tasks" / f"{task_id}.md"

    doc_path = None
    if running_doc.exists():
        doc_path = running_doc
    elif completed_doc.exists():
        doc_path = completed_doc
    else:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Task document not found"
        )

    try:
        content = doc_path.read_text(encoding='utf-8')
        modified_at = datetime.fromtimestamp(doc_path.stat().st_mtime).isoformat()

        return TaskDocumentResponse(
            task_id=task_id,
            content=content,
            modified_at=modified_at
        )
    except Exception as e:
        logger.error(f"Failed to read task document: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to read task document"
        )


@router.post("/{task_id}/cancel")
async def cancel_subagent(
    task_id: str,
    user_id: int = Depends(get_current_user_id),
    task_manager = Depends(get_task_manager_for_user)
) -> Dict[str, Any]:
    """
    Cancel a running Sub Agent task.
    """
    task = task_manager.get_task(task_id)

    if task is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Task not found"
        )

    if task.status.value not in ("pending", "running"):
        return {
            "success": False,
            "task_id": task_id,
            "message": f"Task is already {task.status.value}"
        }

    task.request_cancel()
    logger.info(f"User {user_id} cancelled Sub Agent task {task_id}")

    return {
        "success": True,
        "task_id": task_id,
        "message": "Cancellation requested"
    }
