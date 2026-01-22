"""Schedule Manager - Manages user-defined scheduled tasks"""

import json
import logging
import re
from dataclasses import dataclass, field, asdict
from datetime import datetime, time, timedelta
from pathlib import Path
from typing import Optional, Dict, List, Any, Callable, Awaitable
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

# Validation constants
TASK_ID_PATTERN = re.compile(r'^[a-zA-Z0-9_]{1,32}$')
TIME_PATTERN = re.compile(r'^([01]?[0-9]|2[0-3]):([0-5][0-9])$')

# Default timezone
DEFAULT_TIMEZONE = "Asia/Shanghai"


# Schedule type constants
SCHEDULE_TYPE_DAILY = "daily"
SCHEDULE_TYPE_WEEKLY = "weekly"
SCHEDULE_TYPE_MONTHLY = "monthly"
SCHEDULE_TYPE_INTERVAL = "interval"
SCHEDULE_TYPE_ONCE = "once"

VALID_SCHEDULE_TYPES = [
    SCHEDULE_TYPE_DAILY,
    SCHEDULE_TYPE_WEEKLY,
    SCHEDULE_TYPE_MONTHLY,
    SCHEDULE_TYPE_INTERVAL,
    SCHEDULE_TYPE_ONCE,
]

# Weekday mapping
WEEKDAY_NAMES = {
    "mon": 0, "tue": 1, "wed": 2, "thu": 3, "fri": 4, "sat": 5, "sun": 6,
    "monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3, "friday": 4, "saturday": 5, "sunday": 6,
    "1": 0, "2": 1, "3": 2, "4": 3, "5": 4, "6": 5, "7": 6,
}


@dataclass
class ScheduledTask:
    """Represents a scheduled task"""
    task_id: str
    name: str
    hour: int  # 0-23
    minute: int  # 0-59
    enabled: bool = True
    last_run: Optional[str] = None  # ISO format datetime
    created_at: Optional[str] = None

    # Schedule type: daily, weekly, monthly, interval, once
    schedule_type: str = SCHEDULE_TYPE_DAILY

    # For weekly: list of weekdays (0=Monday, 6=Sunday)
    weekdays: Optional[List[int]] = None

    # For monthly: day of month (1-31)
    month_day: Optional[int] = None

    # For interval: interval in minutes
    interval_minutes: Optional[int] = None

    # For once: specific run date (YYYY-MM-DD)
    run_date: Optional[str] = None

    # For interval: first execution time (HH:MM or YYYY-MM-DDTHH:MM)
    start_time: Optional[str] = None

    # Execution limits
    max_runs: Optional[int] = None  # None = unlimited
    run_count: int = 0

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "ScheduledTask":
        # Handle backward compatibility - filter out unknown fields
        valid_fields = {f.name for f in cls.__dataclass_fields__.values()}
        filtered_data = {k: v for k, v in data.items() if k in valid_fields}
        return cls(**filtered_data)


@dataclass
class UserScheduleConfig:
    """User's schedule configuration"""
    timezone: str = DEFAULT_TIMEZONE
    tasks: Dict[str, ScheduledTask] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "timezone": self.timezone,
            "tasks": {k: v.to_dict() for k, v in self.tasks.items()}
        }

    @classmethod
    def from_dict(cls, data: dict) -> "UserScheduleConfig":
        tasks = {}
        for task_id, task_data in data.get("tasks", {}).items():
            tasks[task_id] = ScheduledTask.from_dict(task_data)
        return cls(
            timezone=data.get("timezone", DEFAULT_TIMEZONE),
            tasks=tasks
        )


class ScheduleManager:
    """
    Manages scheduled tasks for all users.

    Features:
    - Per-user timezone support
    - Task storage in user's data directory
    - Integration with telegram job_queue
    - Queuing when Sub Agents are full
    """

    def __init__(self, users_base_path: str):
        """
        Initialize ScheduleManager.

        Args:
            users_base_path: Base path for user data directories
        """
        self.users_base_path = Path(users_base_path)
        self._user_configs: Dict[int, UserScheduleConfig] = {}
        self._pending_queue: List[Dict[str, Any]] = []  # Tasks waiting for Sub Agent slot
        self._job_queue = None  # Will be set by set_job_queue()
        self._execute_callback: Optional[Callable] = None

    def set_job_queue(self, job_queue):
        """Set the telegram job queue for scheduling"""
        self._job_queue = job_queue

    def set_execute_callback(
        self,
        callback: Callable[[int, str, str], Awaitable[Optional[str]]]
    ):
        """
        Set callback for executing scheduled tasks.

        Args:
            callback: async function(user_id, task_id, prompt) -> task_result
        """
        self._execute_callback = callback

    def _get_user_schedule_dir(self, user_id: int) -> Path:
        """Get the schedules directory for a user"""
        return self.users_base_path / str(user_id) / "data" / "schedules"

    def _get_user_config_path(self, user_id: int) -> Path:
        """Get the config.json path for a user's schedules"""
        return self._get_user_schedule_dir(user_id) / "config.json"

    def _get_task_dir(self, user_id: int, task_id: str) -> Path:
        """Get the directory for a specific task"""
        return self._get_user_schedule_dir(user_id) / "tasks" / task_id

    def _get_operation_log_path(self, user_id: int) -> Path:
        """Get the operation log path for a user"""
        return self._get_user_schedule_dir(user_id) / "operation_log.jsonl"

    def _log_operation(
        self,
        user_id: int,
        action: str,
        task_id: str,
        details: dict | None = None,
        snapshot: dict | None = None
    ):
        """
        Log a schedule operation.

        Args:
            user_id: User ID
            action: Operation type (create, update, delete)
            task_id: Task ID
            details: Additional details (for create/update)
            snapshot: Full task snapshot (for delete, to allow recovery)
        """
        log_path = self._get_operation_log_path(user_id)
        log_path.parent.mkdir(parents=True, exist_ok=True)

        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "action": action,
            "task_id": task_id
        }

        if details:
            log_entry["details"] = details
        if snapshot:
            log_entry["snapshot"] = snapshot

        try:
            with open(log_path, 'a', encoding='utf-8') as f:
                f.write(json.dumps(log_entry, ensure_ascii=False) + '\n')
            logger.debug(f"Logged operation: {action} {task_id} for user {user_id}")
        except Exception as e:
            logger.error(f"Failed to log operation: {e}")

    def get_operation_logs(self, user_id: int, limit: int = 50) -> list[dict]:
        """
        Get recent operation logs for a user.

        Args:
            user_id: User ID
            limit: Maximum number of logs to return

        Returns:
            List of log entries (newest first)
        """
        log_path = self._get_operation_log_path(user_id)
        if not log_path.exists():
            return []

        logs = []
        try:
            with open(log_path, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            logs.append(json.loads(line))
                        except json.JSONDecodeError:
                            pass
        except Exception as e:
            logger.error(f"Failed to read operation logs: {e}")

        # Return newest first, limited
        return logs[-limit:][::-1]

    @staticmethod
    def validate_task_id(task_id: str) -> tuple[bool, str]:
        """
        Validate task ID format.

        Returns:
            (is_valid, error_message)
        """
        if not task_id:
            return False, "Task ID cannot be empty"
        if not TASK_ID_PATTERN.match(task_id):
            return False, "Task ID must be 1-32 characters, alphanumeric and underscore only"
        return True, ""

    @staticmethod
    def validate_time(time_str: str) -> tuple[bool, int, int, str]:
        """
        Validate and parse time string.

        Args:
            time_str: Time in HH:MM format

        Returns:
            (is_valid, hour, minute, error_message)
        """
        if not time_str:
            return False, 0, 0, "Time cannot be empty"

        match = TIME_PATTERN.match(time_str)
        if not match:
            return False, 0, 0, "Time must be in HH:MM format (00:00-23:59)"

        hour = int(match.group(1))
        minute = int(match.group(2))
        return True, hour, minute, ""

    @staticmethod
    def parse_weekdays(weekdays_str: str) -> tuple[bool, List[int], str]:
        """
        Parse weekdays string like "mon,wed,fri" or "1,3,5".

        Returns:
            (is_valid, weekdays_list, error_message)
        """
        if not weekdays_str:
            return False, [], "Weekdays cannot be empty"

        weekdays = []
        parts = [p.strip().lower() for p in weekdays_str.split(",")]
        for part in parts:
            if part in WEEKDAY_NAMES:
                weekdays.append(WEEKDAY_NAMES[part])
            else:
                return False, [], f"Invalid weekday: {part}"

        # Remove duplicates and sort
        weekdays = sorted(set(weekdays))
        return True, weekdays, ""

    @staticmethod
    def parse_interval(interval_str: str) -> tuple[bool, int, str]:
        """
        Parse interval string like "30m", "2h", "1d".

        Returns:
            (is_valid, minutes, error_message)
        """
        if not interval_str:
            return False, 0, "Interval cannot be empty"

        interval_str = interval_str.strip().lower()

        # Match patterns like 30m, 2h, 1d
        import re
        match = re.match(r'^(\d+)([mhd])$', interval_str)
        if not match:
            return False, 0, "Interval must be like 30m (minutes), 2h (hours), or 1d (days)"

        value = int(match.group(1))
        unit = match.group(2)

        if value <= 0:
            return False, 0, "Interval value must be positive"

        if unit == 'm':
            minutes = value
        elif unit == 'h':
            minutes = value * 60
        elif unit == 'd':
            minutes = value * 60 * 24
        else:
            return False, 0, "Invalid interval unit"

        if minutes < 1:
            return False, 0, "Interval must be at least 1 minute"

        return True, minutes, ""

    @staticmethod
    def format_schedule_type(task: "ScheduledTask") -> str:
        """Format task schedule type for display."""
        schedule_type = task.schedule_type or SCHEDULE_TYPE_DAILY
        time_str = f"{task.hour:02d}:{task.minute:02d}"

        if schedule_type == SCHEDULE_TYPE_DAILY:
            return f"每天 {time_str}"

        elif schedule_type == SCHEDULE_TYPE_WEEKLY:
            weekday_names_cn = ["一", "二", "三", "四", "五", "六", "日"]
            if task.weekdays:
                days = "".join(weekday_names_cn[d] for d in sorted(task.weekdays))
                return f"每周{days} {time_str}"
            return f"每周 {time_str}"

        elif schedule_type == SCHEDULE_TYPE_MONTHLY:
            if task.month_day:
                return f"每月{task.month_day}日 {time_str}"
            return f"每月 {time_str}"

        elif schedule_type == SCHEDULE_TYPE_INTERVAL:
            if task.interval_minutes:
                if task.interval_minutes >= 60 * 24:
                    days = task.interval_minutes // (60 * 24)
                    return f"每 {days} 天"
                elif task.interval_minutes >= 60:
                    hours = task.interval_minutes // 60
                    return f"每 {hours} 小时"
                else:
                    return f"每 {task.interval_minutes} 分钟"
            return "间隔执行"

        elif schedule_type == SCHEDULE_TYPE_ONCE:
            if task.run_date:
                return f"一次性 {task.run_date} {time_str}"
            return f"一次性 {time_str}"

        return schedule_type

    @staticmethod
    def format_run_count(task: "ScheduledTask") -> str:
        """Format run count for display."""
        if task.max_runs:
            return f"{task.run_count}/{task.max_runs}"
        return f"{task.run_count}/∞"

    def _load_user_config(self, user_id: int) -> UserScheduleConfig:
        """Load user's schedule configuration"""
        if user_id in self._user_configs:
            return self._user_configs[user_id]

        config_path = self._get_user_config_path(user_id)
        if config_path.exists():
            try:
                with open(config_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                config = UserScheduleConfig.from_dict(data)
            except Exception as e:
                logger.error(f"Failed to load schedule config for user {user_id}: {e}")
                config = UserScheduleConfig()
        else:
            config = UserScheduleConfig()

        self._user_configs[user_id] = config
        return config

    def _save_user_config(self, user_id: int, config: UserScheduleConfig):
        """Save user's schedule configuration"""
        config_path = self._get_user_config_path(user_id)
        config_path.parent.mkdir(parents=True, exist_ok=True)

        with open(config_path, 'w', encoding='utf-8') as f:
            json.dump(config.to_dict(), f, ensure_ascii=False, indent=2)

        self._user_configs[user_id] = config

    def get_user_timezone(self, user_id: int) -> str:
        """Get user's timezone"""
        config = self._load_user_config(user_id)
        return config.timezone

    def set_user_timezone(self, user_id: int, timezone: str) -> bool:
        """
        Set user's timezone.

        Args:
            user_id: User ID
            timezone: Timezone string (e.g., "Asia/Shanghai", "America/New_York")

        Returns:
            True if successful, False if invalid timezone
        """
        # Validate timezone
        try:
            ZoneInfo(timezone)
        except Exception:
            return False

        config = self._load_user_config(user_id)
        config.timezone = timezone
        self._save_user_config(user_id, config)

        # Reschedule all tasks for this user with new timezone
        self._reschedule_user_tasks(user_id)
        return True

    def get_tasks(self, user_id: int) -> List[ScheduledTask]:
        """Get all tasks for a user"""
        config = self._load_user_config(user_id)
        return list(config.tasks.values())

    def get_task(self, user_id: int, task_id: str) -> Optional[ScheduledTask]:
        """Get a specific task"""
        config = self._load_user_config(user_id)
        return config.tasks.get(task_id)

    def add_task(
        self,
        user_id: int,
        task_id: str,
        name: str,
        hour: int,
        minute: int,
        prompt: str,
        enabled: bool = True,
        schedule_type: str = SCHEDULE_TYPE_DAILY,
        weekdays: Optional[List[int]] = None,
        month_day: Optional[int] = None,
        interval_minutes: Optional[int] = None,
        run_date: Optional[str] = None,
        max_runs: Optional[int] = None,
        start_time: Optional[str] = None
    ) -> bool:
        """
        Add a new scheduled task.

        Args:
            user_id: User ID
            task_id: Unique task identifier (alphanumeric, underscores, max 32 chars)
            name: Display name for the task
            hour: Hour to run (0-23), ignored for interval type
            minute: Minute to run (0-59), ignored for interval type
            prompt: Instructions for the Sub Agent
            enabled: Whether to enable immediately (default True)
            schedule_type: One of daily, weekly, monthly, interval, once
            weekdays: List of weekdays for weekly type (0=Mon, 6=Sun)
            month_day: Day of month for monthly type (1-31)
            interval_minutes: Interval in minutes for interval type
            run_date: Date string (YYYY-MM-DD) for once type
            max_runs: Maximum number of executions (None = unlimited)
            start_time: First execution time for interval type (HH:MM or YYYY-MM-DDTHH:MM)

        Returns:
            True if successful
        """
        # Validate task_id: alphanumeric + underscore, max 32 chars
        if not task_id.replace("_", "").isalnum():
            return False
        if len(task_id) > 32:
            return False

        # Validate schedule_type
        if schedule_type not in VALID_SCHEDULE_TYPES:
            return False

        # Validate time for non-interval types
        if schedule_type != SCHEDULE_TYPE_INTERVAL:
            if not (0 <= hour <= 23 and 0 <= minute <= 59):
                return False

        # Validate type-specific parameters
        if schedule_type == SCHEDULE_TYPE_WEEKLY and weekdays:
            if not all(0 <= d <= 6 for d in weekdays):
                return False

        if schedule_type == SCHEDULE_TYPE_MONTHLY and month_day:
            if not (1 <= month_day <= 31):
                return False

        if schedule_type == SCHEDULE_TYPE_INTERVAL:
            if not interval_minutes or interval_minutes <= 0:
                return False

        if schedule_type == SCHEDULE_TYPE_ONCE:
            if not run_date:
                return False
            try:
                datetime.strptime(run_date, "%Y-%m-%d")
            except ValueError:
                return False

        config = self._load_user_config(user_id)

        # Create task
        task = ScheduledTask(
            task_id=task_id,
            name=name,
            hour=hour,
            minute=minute,
            enabled=enabled,
            created_at=datetime.now().isoformat(),
            schedule_type=schedule_type,
            weekdays=weekdays,
            month_day=month_day,
            interval_minutes=interval_minutes,
            run_date=run_date,
            start_time=start_time,
            max_runs=max_runs,
            run_count=0
        )

        # Save task config
        config.tasks[task_id] = task
        self._save_user_config(user_id, config)

        # Save prompt file
        task_dir = self._get_task_dir(user_id, task_id)
        task_dir.mkdir(parents=True, exist_ok=True)
        prompt_path = task_dir / "prompt.txt"
        with open(prompt_path, 'w', encoding='utf-8') as f:
            f.write(prompt)

        # Schedule the task
        self._schedule_task(user_id, task)

        # Log operation
        log_details = {
            "name": name,
            "schedule_type": schedule_type,
            "enabled": enabled,
            "prompt_length": len(prompt)
        }
        if schedule_type == SCHEDULE_TYPE_INTERVAL:
            log_details["interval_minutes"] = interval_minutes
        else:
            log_details["time"] = f"{hour:02d}:{minute:02d}"
        if weekdays:
            log_details["weekdays"] = weekdays
        if month_day:
            log_details["month_day"] = month_day
        if run_date:
            log_details["run_date"] = run_date
        if start_time:
            log_details["start_time"] = start_time
        if max_runs:
            log_details["max_runs"] = max_runs

        self._log_operation(user_id, "create", task_id, details=log_details)

        logger.info(f"User {user_id} added {schedule_type} task: {task_id}")
        return True

    def update_task_prompt(self, user_id: int, task_id: str, prompt: str) -> bool:
        """Update the prompt for a task"""
        config = self._load_user_config(user_id)
        if task_id not in config.tasks:
            return False

        task_dir = self._get_task_dir(user_id, task_id)
        prompt_path = task_dir / "prompt.txt"
        with open(prompt_path, 'w', encoding='utf-8') as f:
            f.write(prompt)

        # Log operation
        self._log_operation(user_id, "update", task_id, details={
            "field": "prompt",
            "new_prompt_length": len(prompt)
        })

        return True

    def update_task(
        self,
        user_id: int,
        task_id: str,
        name: str | None = None,
        hour: int | None = None,
        minute: int | None = None,
        prompt: str | None = None,
        enabled: bool | None = None,
        schedule_type: str | None = None,
        weekdays: List[int] | None = None,
        month_day: int | None = None,
        interval_minutes: int | None = None,
        run_date: str | None = None,
        max_runs: int | None = None,
        reset_run_count: bool = False
    ) -> tuple[bool, str]:
        """
        Update a scheduled task.

        Args:
            user_id: User ID
            task_id: Task ID to update
            name: New name (optional)
            hour: New hour (optional)
            minute: New minute (optional)
            prompt: New prompt (optional)
            enabled: New enabled state (optional)
            schedule_type: New schedule type (optional)
            weekdays: New weekdays list (optional)
            month_day: New month day (optional)
            interval_minutes: New interval (optional)
            run_date: New run date (optional)
            max_runs: New max runs (optional, use -1 to clear limit)
            reset_run_count: If True, reset run_count to 0

        Returns:
            (success, error_message)
        """
        config = self._load_user_config(user_id)
        if task_id not in config.tasks:
            return False, f"Task '{task_id}' not found"

        task = config.tasks[task_id]
        changes = {}
        need_reschedule = False

        # Update name
        if name is not None:
            changes["name"] = f"{task.name} -> {name}"
            task.name = name

        # Update time
        if hour is not None or minute is not None:
            old_time = f"{task.hour:02d}:{task.minute:02d}"
            if hour is not None:
                task.hour = hour
            if minute is not None:
                task.minute = minute
            new_time = f"{task.hour:02d}:{task.minute:02d}"
            changes["time"] = f"{old_time} -> {new_time}"
            need_reschedule = True

        # Update schedule_type
        if schedule_type is not None and schedule_type != task.schedule_type:
            if schedule_type not in VALID_SCHEDULE_TYPES:
                return False, f"Invalid schedule_type: {schedule_type}"
            changes["schedule_type"] = f"{task.schedule_type} -> {schedule_type}"
            task.schedule_type = schedule_type
            need_reschedule = True

        # Update weekdays
        if weekdays is not None:
            if weekdays and not all(0 <= d <= 6 for d in weekdays):
                return False, "Invalid weekdays (must be 0-6)"
            old_weekdays = task.weekdays or []
            changes["weekdays"] = f"{old_weekdays} -> {weekdays}"
            task.weekdays = weekdays if weekdays else None
            need_reschedule = True

        # Update month_day
        if month_day is not None:
            if month_day != 0 and not (1 <= month_day <= 31):
                return False, "Invalid month_day (must be 1-31)"
            changes["month_day"] = f"{task.month_day} -> {month_day if month_day else None}"
            task.month_day = month_day if month_day else None
            need_reschedule = True

        # Update interval_minutes
        if interval_minutes is not None:
            if interval_minutes > 0:
                changes["interval_minutes"] = f"{task.interval_minutes} -> {interval_minutes}"
                task.interval_minutes = interval_minutes
                need_reschedule = True
            elif interval_minutes == 0:
                task.interval_minutes = None

        # Update run_date
        if run_date is not None:
            if run_date:
                try:
                    datetime.strptime(run_date, "%Y-%m-%d")
                except ValueError:
                    return False, "Invalid run_date format (use YYYY-MM-DD)"
            changes["run_date"] = f"{task.run_date} -> {run_date if run_date else None}"
            task.run_date = run_date if run_date else None
            need_reschedule = True

        # Update max_runs
        if max_runs is not None:
            if max_runs == -1:
                # Clear the limit
                changes["max_runs"] = f"{task.max_runs} -> unlimited"
                task.max_runs = None
            elif max_runs > 0:
                changes["max_runs"] = f"{task.max_runs} -> {max_runs}"
                task.max_runs = max_runs

        # Reset run count
        if reset_run_count:
            changes["run_count"] = f"{task.run_count} -> 0"
            task.run_count = 0

        # Update enabled
        if enabled is not None and enabled != task.enabled:
            changes["enabled"] = f"{task.enabled} -> {enabled}"
            task.enabled = enabled
            if enabled:
                need_reschedule = True
            else:
                self._unschedule_task(user_id, task_id)

        # Save config
        self._save_user_config(user_id, config)

        # Update prompt if provided
        if prompt is not None:
            task_dir = self._get_task_dir(user_id, task_id)
            prompt_path = task_dir / "prompt.txt"
            with open(prompt_path, 'w', encoding='utf-8') as f:
                f.write(prompt)
            changes["prompt"] = f"updated ({len(prompt)} chars)"

        # Reschedule if needed
        if need_reschedule and task.enabled:
            self._schedule_task(user_id, task)

        # Log operation
        if changes:
            self._log_operation(user_id, "update", task_id, details={"changes": changes})

        return True, ""

    def get_task_prompt(self, user_id: int, task_id: str) -> Optional[str]:
        """Get the prompt for a task"""
        task_dir = self._get_task_dir(user_id, task_id)
        prompt_path = task_dir / "prompt.txt"
        if prompt_path.exists():
            with open(prompt_path, 'r', encoding='utf-8') as f:
                return f.read()
        return None

    def delete_task(self, user_id: int, task_id: str) -> bool:
        """Delete a scheduled task"""
        config = self._load_user_config(user_id)
        if task_id not in config.tasks:
            return False

        # Save snapshot before deletion (for recovery)
        task = config.tasks[task_id]
        prompt = self.get_task_prompt(user_id, task_id)
        snapshot = {
            "task": task.to_dict(),
            "prompt": prompt
        }

        # Remove from config
        del config.tasks[task_id]
        self._save_user_config(user_id, config)

        # Remove task directory
        import shutil
        task_dir = self._get_task_dir(user_id, task_id)
        if task_dir.exists():
            shutil.rmtree(task_dir)

        # Remove from job queue
        self._unschedule_task(user_id, task_id)

        # Log operation with full snapshot
        self._log_operation(user_id, "delete", task_id, snapshot=snapshot)

        logger.info(f"User {user_id} deleted scheduled task: {task_id}")
        return True

    def enable_task(self, user_id: int, task_id: str) -> bool:
        """Enable a task"""
        config = self._load_user_config(user_id)
        if task_id not in config.tasks:
            return False

        config.tasks[task_id].enabled = True
        self._save_user_config(user_id, config)
        self._schedule_task(user_id, config.tasks[task_id])
        return True

    def disable_task(self, user_id: int, task_id: str) -> bool:
        """Disable a task"""
        config = self._load_user_config(user_id)
        if task_id not in config.tasks:
            return False

        config.tasks[task_id].enabled = False
        self._save_user_config(user_id, config)
        self._unschedule_task(user_id, task_id)
        return True

    def _get_job_name(self, user_id: int, task_id: str) -> str:
        """Generate unique job name for telegram job queue"""
        return f"schedule_{user_id}_{task_id}"

    def _schedule_task(self, user_id: int, task: ScheduledTask):
        """Schedule a task in the job queue based on schedule_type"""
        if not self._job_queue or not task.enabled:
            return

        # Check if already reached max runs
        if task.max_runs is not None and task.run_count >= task.max_runs:
            logger.debug(f"Task {task.task_id} already reached max runs ({task.run_count}/{task.max_runs})")
            return

        job_name = self._get_job_name(user_id, task.task_id)

        # Remove existing job if any
        self._unschedule_task(user_id, task.task_id)

        # Get user's timezone
        config = self._load_user_config(user_id)
        try:
            tz = ZoneInfo(config.timezone)
        except Exception:
            tz = ZoneInfo(DEFAULT_TIMEZONE)

        # Create the job callback
        async def job_callback(context):
            await self._execute_scheduled_task(user_id, task.task_id)

        schedule_type = task.schedule_type or SCHEDULE_TYPE_DAILY

        if schedule_type == SCHEDULE_TYPE_INTERVAL:
            # Interval-based scheduling
            if not task.interval_minutes or task.interval_minutes <= 0:
                logger.error(f"Invalid interval_minutes for task {task.task_id}")
                return

            # Calculate first execution time
            first_run = None
            if task.start_time:
                try:
                    # Try parsing as full datetime (YYYY-MM-DDTHH:MM)
                    if "T" in task.start_time or "-" in task.start_time:
                        if "T" in task.start_time:
                            first_run = datetime.strptime(task.start_time, "%Y-%m-%dT%H:%M")
                        else:
                            # YYYY-MM-DD HH:MM format
                            first_run = datetime.strptime(task.start_time, "%Y-%m-%d %H:%M")
                        first_run = first_run.replace(tzinfo=tz)
                    else:
                        # Try parsing as time only (HH:MM) - use today or tomorrow
                        parts = task.start_time.split(":")
                        start_hour, start_minute = int(parts[0]), int(parts[1])
                        now = datetime.now(tz)
                        first_run = now.replace(hour=start_hour, minute=start_minute, second=0, microsecond=0)
                        # If time has passed today, schedule for tomorrow
                        if first_run <= now:
                            first_run += timedelta(days=1)

                    # Check if start time has passed
                    now = datetime.now(tz)
                    if first_run <= now:
                        logger.debug(f"Interval task {task.task_id} start_time has passed, starting immediately")
                        first_run = None
                except Exception as e:
                    logger.warning(f"Failed to parse start_time '{task.start_time}' for task {task.task_id}: {e}")
                    first_run = None

            self._job_queue.run_repeating(
                job_callback,
                interval=task.interval_minutes * 60,  # Convert to seconds
                first=first_run,
                name=job_name,
                data={"user_id": user_id, "task_id": task.task_id}
            )
            if first_run:
                logger.debug(f"Scheduled interval task {task.task_id} for user {user_id} starting at {first_run}, every {task.interval_minutes} minutes")
            else:
                logger.debug(f"Scheduled interval task {task.task_id} for user {user_id} every {task.interval_minutes} minutes (immediate start)")

        elif schedule_type == SCHEDULE_TYPE_ONCE:
            # One-time scheduling
            if not task.run_date:
                logger.error(f"No run_date for once task {task.task_id}")
                return

            try:
                # Parse run_date and combine with hour:minute
                run_date = datetime.strptime(task.run_date, "%Y-%m-%d").date()
                run_datetime = datetime.combine(
                    run_date,
                    time(hour=task.hour, minute=task.minute),
                    tzinfo=tz
                )

                # Check if time has passed
                now = datetime.now(tz)
                if run_datetime <= now:
                    logger.debug(f"Once task {task.task_id} time has already passed")
                    return

                self._job_queue.run_once(
                    job_callback,
                    when=run_datetime,
                    name=job_name,
                    data={"user_id": user_id, "task_id": task.task_id}
                )
                logger.debug(f"Scheduled once task {task.task_id} for user {user_id} at {run_datetime}")

            except ValueError as e:
                logger.error(f"Invalid run_date format for task {task.task_id}: {e}")
                return

        else:
            # Daily, weekly, monthly - all use run_daily, but callback checks the day
            run_time = time(hour=task.hour, minute=task.minute, tzinfo=tz)
            self._job_queue.run_daily(
                job_callback,
                time=run_time,
                name=job_name,
                data={"user_id": user_id, "task_id": task.task_id}
            )
            logger.debug(f"Scheduled {schedule_type} task {task.task_id} for user {user_id} at {task.hour:02d}:{task.minute:02d} {config.timezone}")

    def _unschedule_task(self, user_id: int, task_id: str):
        """Remove a task from the job queue"""
        if not self._job_queue:
            return

        job_name = self._get_job_name(user_id, task_id)
        jobs = self._job_queue.get_jobs_by_name(job_name)
        for job in jobs:
            job.schedule_removal()

    def _reschedule_user_tasks(self, user_id: int):
        """Reschedule all tasks for a user (e.g., after timezone change)"""
        config = self._load_user_config(user_id)
        for task in config.tasks.values():
            if task.enabled:
                self._schedule_task(user_id, task)

    def _should_run_today(self, task: ScheduledTask, tz: ZoneInfo) -> bool:
        """
        Check if a task should run today based on its schedule_type.
        Used for weekly and monthly tasks that are scheduled daily but only run on specific days.
        """
        schedule_type = task.schedule_type or SCHEDULE_TYPE_DAILY

        if schedule_type == SCHEDULE_TYPE_DAILY:
            return True

        if schedule_type == SCHEDULE_TYPE_INTERVAL:
            return True  # Interval tasks always run when triggered

        if schedule_type == SCHEDULE_TYPE_ONCE:
            return True  # Once tasks always run when triggered

        now = datetime.now(tz)

        if schedule_type == SCHEDULE_TYPE_WEEKLY:
            if not task.weekdays:
                return True  # No weekdays specified, run every day
            current_weekday = now.weekday()  # 0=Monday, 6=Sunday
            return current_weekday in task.weekdays

        if schedule_type == SCHEDULE_TYPE_MONTHLY:
            if not task.month_day:
                return True  # No day specified, run every day
            current_day = now.day
            # Handle months with fewer days (e.g., 31 in Feb runs on last day)
            import calendar
            last_day_of_month = calendar.monthrange(now.year, now.month)[1]
            if task.month_day > last_day_of_month:
                return current_day == last_day_of_month
            return current_day == task.month_day

        return True

    async def _execute_scheduled_task(self, user_id: int, task_id: str):
        """Execute a scheduled task"""
        config = self._load_user_config(user_id)
        task = config.tasks.get(task_id)

        if not task or not task.enabled:
            return

        # Get user's timezone
        try:
            tz = ZoneInfo(config.timezone)
        except Exception:
            tz = ZoneInfo(DEFAULT_TIMEZONE)

        # Check if should run today (for weekly/monthly)
        if not self._should_run_today(task, tz):
            logger.debug(f"Task {task_id} skipped - not scheduled for today")
            return

        # Check if already reached max runs
        if task.max_runs is not None and task.run_count >= task.max_runs:
            logger.debug(f"Task {task_id} skipped - already reached max runs ({task.run_count}/{task.max_runs})")
            # Auto-disable the task
            task.enabled = False
            self._save_user_config(user_id, config)
            self._unschedule_task(user_id, task_id)
            return

        # Get prompt
        prompt = self.get_task_prompt(user_id, task_id)
        if not prompt:
            logger.error(f"No prompt found for task {task_id}")
            return

        # Update run count and last_run BEFORE executing
        task.run_count += 1
        task.last_run = datetime.now().isoformat()

        # Check if this is the last run
        is_last_run = task.max_runs is not None and task.run_count >= task.max_runs
        is_once_task = task.schedule_type == SCHEDULE_TYPE_ONCE

        # Auto-disable if reached max runs or is once task
        if is_last_run or is_once_task:
            task.enabled = False
            self._unschedule_task(user_id, task_id)
            logger.info(f"Task {task_id} auto-disabled after run {task.run_count}" +
                       (f"/{task.max_runs}" if task.max_runs else " (once task)"))

        self._save_user_config(user_id, config)

        logger.info(f"Executing scheduled task {task_id} for user {user_id} (run {task.run_count}" +
                   (f"/{task.max_runs})" if task.max_runs else ")"))

        # Execute via callback
        if self._execute_callback:
            try:
                await self._execute_callback(user_id, task_id, prompt)
            except Exception as e:
                logger.error(f"Failed to execute scheduled task {task_id}: {e}")
        else:
            logger.warning("No execute callback set for schedule manager")

    def initialize_all_schedules(self):
        """Load and schedule all user tasks on startup"""
        if not self.users_base_path.exists():
            return

        for user_dir in self.users_base_path.iterdir():
            if not user_dir.is_dir():
                continue

            try:
                user_id = int(user_dir.name)
            except ValueError:
                continue

            config = self._load_user_config(user_id)
            for task in config.tasks.values():
                if task.enabled:
                    self._schedule_task(user_id, task)

        logger.info("Initialized all user schedules")

    def get_pending_queue_size(self) -> int:
        """Get number of tasks waiting in queue"""
        return len(self._pending_queue)
