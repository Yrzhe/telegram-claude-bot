"""Tasks API routes."""

import logging
from typing import Optional, List, Dict, Any
from datetime import datetime

from fastapi import APIRouter, HTTPException, status, Depends, Query
from pydantic import BaseModel

from ..dependencies import (
    get_current_user_id,
    get_task_manager_for_user
)

logger = logging.getLogger(__name__)

router = APIRouter()


class TaskInfo(BaseModel):
    """Task information."""
    task_id: str
    description: str
    status: str
    created_at: str
    result: Optional[str] = None
    error: Optional[str] = None


class TaskStats(BaseModel):
    """Task statistics."""
    pending: int
    running: int
    completed: int
    failed: int
    cancelled: int


class TaskListResponse(BaseModel):
    """Response for task listing."""
    running: List[TaskInfo]
    recent_completed: List[TaskInfo]
    stats: TaskStats


class TaskDetailResponse(BaseModel):
    """Detailed task response."""
    task_id: str
    description: str
    status: str
    created_at: str
    result: Optional[str] = None
    error: Optional[str] = None
    needs_review: bool = False
    retry_count: int = 0
    max_retries: int = 0


class CancelResponse(BaseModel):
    """Response for task cancellation."""
    success: bool
    task_id: str
    message: str


@router.get("", response_model=TaskListResponse)
async def list_tasks(
    user_id: int = Depends(get_current_user_id),
    task_manager = Depends(get_task_manager_for_user)
):
    """
    List all tasks (running and recent completed).
    """
    # Get all tasks
    all_tasks = task_manager.get_all_tasks()

    running = []
    recent_completed = []

    for task in all_tasks:
        task_info = TaskInfo(
            task_id=task["task_id"],
            description=task["description"],
            status=task["status"],
            created_at=task["created_at"],
            result=task.get("result"),
            error=task.get("error")
        )

        if task["status"] in ("pending", "running"):
            running.append(task_info)
        else:
            recent_completed.append(task_info)

    # Get stats
    stats_dict = task_manager.get_status_summary()
    stats = TaskStats(
        pending=stats_dict.get("pending", 0),
        running=stats_dict.get("running", 0),
        completed=stats_dict.get("completed", 0),
        failed=stats_dict.get("failed", 0),
        cancelled=stats_dict.get("cancelled", 0)
    )

    # Limit recent completed to 20
    recent_completed = recent_completed[:20]

    return TaskListResponse(
        running=running,
        recent_completed=recent_completed,
        stats=stats
    )


@router.get("/{task_id}", response_model=TaskDetailResponse)
async def get_task(
    task_id: str,
    user_id: int = Depends(get_current_user_id),
    task_manager = Depends(get_task_manager_for_user)
):
    """
    Get detailed information about a specific task.
    """
    task = task_manager.get_task(task_id)

    if task is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Task not found"
        )

    return TaskDetailResponse(
        task_id=task.task_id,
        description=task.description,
        status=task.status.value,
        created_at=task.created_at.strftime('%Y-%m-%d %H:%M:%S'),
        result=task.result,
        error=task.error,
        needs_review=task.needs_review,
        retry_count=task.retry_count,
        max_retries=task.max_retries
    )


@router.post("/{task_id}/cancel", response_model=CancelResponse)
async def cancel_task(
    task_id: str,
    user_id: int = Depends(get_current_user_id),
    task_manager = Depends(get_task_manager_for_user)
):
    """
    Cancel a running task.
    """
    task = task_manager.get_task(task_id)

    if task is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Task not found"
        )

    if task.status.value not in ("pending", "running"):
        return CancelResponse(
            success=False,
            task_id=task_id,
            message=f"Task is already {task.status.value}"
        )

    # Request cancellation
    task.request_cancel()
    logger.info(f"User {user_id} cancelled task {task_id}")

    return CancelResponse(
        success=True,
        task_id=task_id,
        message="Cancellation requested"
    )


@router.get("/history/all")
async def get_task_history(
    limit: int = Query(50, ge=1, le=100),
    user_id: int = Depends(get_current_user_id),
    task_manager = Depends(get_task_manager_for_user)
) -> List[Dict[str, Any]]:
    """
    Get task history from completed task documents.
    """
    # Get completed task documents
    docs = task_manager.get_completed_task_documents(limit=limit)

    history = []
    for doc_path in docs:
        try:
            stat = doc_path.stat()
            history.append({
                "task_id": doc_path.stem,
                "file": doc_path.name,
                "completed_at": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                "size": stat.st_size
            })
        except Exception:
            continue

    return history
