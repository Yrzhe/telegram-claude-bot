"""Schedules API routes."""

import logging
from typing import Optional, List, Dict, Any
from datetime import datetime

from fastapi import APIRouter, HTTPException, status, Depends, Query
from pydantic import BaseModel

from ..dependencies import (
    get_current_user_id,
    get_schedule_manager
)

logger = logging.getLogger(__name__)

router = APIRouter()


class ScheduleInfo(BaseModel):
    """Scheduled task information."""
    task_id: str
    name: str
    schedule_type: str
    time: str
    enabled: bool
    last_run: Optional[str] = None
    run_count: int = 0
    max_runs: Optional[int] = None
    weekdays: Optional[List[int]] = None
    month_day: Optional[int] = None
    interval_minutes: Optional[int] = None
    run_date: Optional[str] = None
    schedule_display: str  # Human-readable schedule description


class ScheduleListResponse(BaseModel):
    """Response for schedule listing."""
    timezone: str
    tasks: List[ScheduleInfo]
    active_count: int
    total_count: int


class ScheduleDetailResponse(BaseModel):
    """Detailed schedule response."""
    task_id: str
    name: str
    schedule_type: str
    hour: int
    minute: int
    enabled: bool
    created_at: Optional[str] = None
    last_run: Optional[str] = None
    run_count: int = 0
    max_runs: Optional[int] = None
    weekdays: Optional[List[int]] = None
    month_day: Optional[int] = None
    interval_minutes: Optional[int] = None
    run_date: Optional[str] = None
    prompt: Optional[str] = None


class OperationLog(BaseModel):
    """Schedule operation log entry."""
    timestamp: str
    action: str
    task_id: str
    details: Optional[Dict[str, Any]] = None
    snapshot: Optional[Dict[str, Any]] = None


class OperationLogsResponse(BaseModel):
    """Response for operation logs."""
    logs: List[OperationLog]


@router.get("", response_model=ScheduleListResponse)
async def list_schedules(
    user_id: int = Depends(get_current_user_id),
    schedule_manager = Depends(get_schedule_manager)
):
    """
    List all scheduled tasks for the user.
    """
    # Get user's timezone
    timezone = schedule_manager.get_user_timezone(user_id)

    # Get all tasks
    tasks = schedule_manager.get_tasks(user_id)

    schedule_list = []
    active_count = 0

    for task in tasks:
        if task.enabled:
            active_count += 1

        schedule_list.append(ScheduleInfo(
            task_id=task.task_id,
            name=task.name,
            schedule_type=task.schedule_type or "daily",
            time=f"{task.hour:02d}:{task.minute:02d}",
            enabled=task.enabled,
            last_run=task.last_run,
            run_count=task.run_count,
            max_runs=task.max_runs,
            weekdays=task.weekdays,
            month_day=task.month_day,
            interval_minutes=task.interval_minutes,
            run_date=task.run_date,
            schedule_display=schedule_manager.format_schedule_type(task)
        ))

    # Sort: enabled first, then by name
    schedule_list.sort(key=lambda s: (not s.enabled, s.name.lower()))

    return ScheduleListResponse(
        timezone=timezone,
        tasks=schedule_list,
        active_count=active_count,
        total_count=len(tasks)
    )


@router.get("/logs", response_model=OperationLogsResponse)
async def get_operation_logs(
    limit: int = Query(50, ge=1, le=200),
    user_id: int = Depends(get_current_user_id),
    schedule_manager = Depends(get_schedule_manager)
):
    """
    Get schedule operation logs (create, update, delete history).
    """
    logs = schedule_manager.get_operation_logs(user_id, limit=limit)

    return OperationLogsResponse(
        logs=[
            OperationLog(
                timestamp=log.get("timestamp", ""),
                action=log.get("action", ""),
                task_id=log.get("task_id", ""),
                details=log.get("details"),
                snapshot=log.get("snapshot")
            )
            for log in logs
        ]
    )


@router.get("/{task_id}", response_model=ScheduleDetailResponse)
async def get_schedule(
    task_id: str,
    user_id: int = Depends(get_current_user_id),
    schedule_manager = Depends(get_schedule_manager)
):
    """
    Get detailed information about a specific scheduled task.
    """
    task = schedule_manager.get_task(user_id, task_id)

    if task is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Scheduled task not found"
        )

    # Get the prompt
    prompt = schedule_manager.get_task_prompt(user_id, task_id)

    return ScheduleDetailResponse(
        task_id=task.task_id,
        name=task.name,
        schedule_type=task.schedule_type or "daily",
        hour=task.hour,
        minute=task.minute,
        enabled=task.enabled,
        created_at=task.created_at,
        last_run=task.last_run,
        run_count=task.run_count,
        max_runs=task.max_runs,
        weekdays=task.weekdays,
        month_day=task.month_day,
        interval_minutes=task.interval_minutes,
        run_date=task.run_date,
        prompt=prompt
    )


@router.get("/history/executions")
async def get_execution_history(
    limit: int = Query(50, ge=1, le=200),
    user_id: int = Depends(get_current_user_id),
    schedule_manager = Depends(get_schedule_manager)
) -> List[Dict[str, Any]]:
    """
    Get schedule execution history.

    This reads from the operation logs and filters for execution-related entries.
    """
    logs = schedule_manager.get_operation_logs(user_id, limit=limit * 2)

    # Filter and format execution-related logs
    executions = []
    tasks = {t.task_id: t for t in schedule_manager.get_tasks(user_id)}

    for log in logs:
        task_id = log.get("task_id", "")
        task = tasks.get(task_id)
        task_name = task.name if task else task_id

        # Include create/update/delete actions
        executions.append({
            "timestamp": log.get("timestamp"),
            "task_id": task_id,
            "task_name": task_name,
            "action": log.get("action"),
            "details": log.get("details")
        })

        if len(executions) >= limit:
            break

    return executions
