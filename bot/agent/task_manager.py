"""Sub Agent Task Manager - Manages background tasks executed by Sub Agents"""

import asyncio
import logging
import shutil
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Callable, Awaitable, Any, Dict, List, Tuple
from enum import Enum
from datetime import datetime

from ..file_tracker import FileTracker, send_tracked_files

logger = logging.getLogger(__name__)


class TaskStatus(Enum):
    """Task status enum"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    FAILED = "failed"


@dataclass
class SubAgentTask:
    """Represents a Sub Agent task"""
    task_id: str
    parent_message_id: str  # ID of the user message that triggered this task
    description: str
    created_at: datetime = field(default_factory=datetime.now)
    status: TaskStatus = TaskStatus.PENDING
    result: Optional[str] = None
    error: Optional[str] = None
    _cancel_event: asyncio.Event = field(default_factory=asyncio.Event)
    _asyncio_task: Optional[asyncio.Task] = None

    # Review-related fields
    needs_review: bool = False           # Whether this task requires automatic quality review
    review_criteria: str = ""            # Criteria for judging result quality
    retry_count: int = 0                 # Current retry count
    max_retries: int = 10                # Maximum number of retries
    retry_history: List[Dict] = field(default_factory=list)  # History of retries
    original_prompt: str = ""            # Original prompt for retries

    def request_cancel(self):
        """Request cancellation of this task"""
        self._cancel_event.set()
        if self._asyncio_task and not self._asyncio_task.done():
            self._asyncio_task.cancel()

    def is_cancel_requested(self) -> bool:
        """Check if cancellation was requested"""
        return self._cancel_event.is_set()

    def add_retry_history(
        self,
        result: str,
        feedback: str,
        suggestions: List[str] = None,
        missing_dimensions: List[str] = None
    ):
        """
        Add a retry record to history with enhanced information.

        Args:
            result: The result that was rejected
            feedback: Why it was rejected
            suggestions: Specific directions to explore in next attempt
            missing_dimensions: What aspects were missing
        """
        self.retry_history.append({
            "attempt": self.retry_count,
            "result_summary": result[:500] if len(result) > 500 else result,
            "feedback": feedback,
            "suggestions": suggestions or [],
            "missing_dimensions": missing_dimensions or [],
            "timestamp": datetime.now().isoformat()
        })


class TaskManager:
    """
    Manages Sub Agent tasks for a single user.

    Features:
    - Track up to MAX_SUB_AGENTS concurrent tasks
    - Cancel tasks by parent message ID
    - Collect completed results
    - Automatic notification when tasks complete
    - Task documents in running_tasks/ and completed_tasks/ folders
    """

    MAX_SUB_AGENTS = 10

    def __init__(
        self,
        user_id: int,
        on_task_complete: Optional[Callable[[str, str, str], Awaitable[None]]] = None,
        working_directory: Optional[str] = None,
        send_file_callback: Optional[Callable[[str, Optional[str]], Awaitable[bool]]] = None,
        send_message_callback: Optional[Callable[[str], Awaitable[None]]] = None
    ):
        """
        Args:
            user_id: User ID
            on_task_complete: Callback(task_id, description, result) called when task completes
            working_directory: User's working directory for task documents
            send_file_callback: Callback to send files to user
            send_message_callback: Callback to send messages to user
        """
        self.user_id = user_id
        self._tasks: Dict[str, SubAgentTask] = {}
        self._lock = asyncio.Lock()
        self._on_task_complete = on_task_complete
        self._working_directory = Path(working_directory) if working_directory else None
        self._send_file_callback = send_file_callback
        self._send_message_callback = send_message_callback

    def _get_running_tasks_dir(self) -> Optional[Path]:
        """Get the running_tasks directory"""
        if not self._working_directory:
            return None
        running_dir = self._working_directory / "data" / "running_tasks"
        running_dir.mkdir(parents=True, exist_ok=True)
        return running_dir

    def _get_completed_tasks_dir(self) -> Optional[Path]:
        """Get the completed_tasks directory"""
        if not self._working_directory:
            return None
        completed_dir = self._working_directory / "data" / "completed_tasks"
        completed_dir.mkdir(parents=True, exist_ok=True)
        return completed_dir

    async def _send_task_files(self, tracker: FileTracker) -> Tuple[int, List[str]]:
        """
        Send files created during task execution to user.

        Args:
            tracker: FileTracker that tracked files during execution

        Returns:
            Tuple of (files_sent_count, list_of_relative_paths)
        """
        if not self._send_file_callback or not self._working_directory:
            return 0, []

        new_files = tracker.get_new_files()
        if not new_files:
            return 0, []

        # Get relative paths for result message
        relative_paths = []
        for f in new_files:
            try:
                rel = f.relative_to(self._working_directory)
                relative_paths.append(str(rel))
            except ValueError:
                relative_paths.append(f.name)

        # Send files to user
        sent_count = await send_tracked_files(
            files=new_files,
            working_dir=self._working_directory,
            send_file_callback=self._send_file_callback,
            send_message_callback=self._send_message_callback
        )

        logger.info(f"Sent {sent_count} task files to user {self.user_id}")
        return sent_count, relative_paths

    async def _save_and_send_review_log(
        self,
        task_id: str,
        description: str,
        review_log: List[Dict]
    ) -> Optional[Path]:
        """
        Save review log to file and send to user.

        Args:
            task_id: Task ID
            description: Task description
            review_log: List of attempt records

        Returns:
            Path to the log file if created
        """
        if not self._working_directory or not review_log:
            return None

        # Create logs directory
        logs_dir = self._working_directory / "data" / "review_logs"
        logs_dir.mkdir(parents=True, exist_ok=True)

        # Generate log content
        log_path = logs_dir / f"review_{task_id}.md"
        content = f"""# Review Log: {description}

**Task ID:** {task_id}
**Total Attempts:** {len(review_log)}
**Final Status:** {review_log[-1].get('status', 'Unknown')}

---

"""
        for entry in review_log:
            attempt = entry.get('attempt', '?')
            timestamp = entry.get('timestamp', 'N/A')
            status = entry.get('status', 'Unknown')

            content += f"""## Attempt {attempt}

**Time:** {timestamp}
**Status:** {'✅ PASSED' if status == 'PASSED' else '❌ REJECTED'}

"""
            if status == 'REJECTED':
                feedback = entry.get('feedback', '')
                if feedback:
                    content += f"**Rejection Reason:** {feedback}\n\n"

                missing = entry.get('missing_dimensions', [])
                if missing:
                    content += "**Missing Dimensions:**\n"
                    for m in missing:
                        content += f"- {m}\n"
                    content += "\n"

                suggestions = entry.get('suggestions', [])
                if suggestions:
                    content += "**Improvement Directions:**\n"
                    for s in suggestions:
                        content += f"- {s}\n"
                    content += "\n"

            result_preview = entry.get('result_preview', '')
            if result_preview:
                # Truncate for log file
                preview = result_preview[:500] + "..." if len(result_preview) > 500 else result_preview
                content += f"**Result Preview:**\n```\n{preview}\n```\n\n"

            content += "---\n\n"

        # Save log file
        try:
            with open(log_path, 'w', encoding='utf-8') as f:
                f.write(content)
            logger.info(f"Saved review log: {log_path}")

            # Send log file to user
            if self._send_file_callback:
                try:
                    await self._send_file_callback(str(log_path), f"📋 Review log ({len(review_log)} attempts)")
                except Exception as e:
                    logger.error(f"Failed to send review log file: {e}")

            return log_path
        except Exception as e:
            logger.error(f"Failed to save review log: {e}")
            return None

    def _create_task_document(self, task: SubAgentTask, prompt: str = "") -> Optional[Path]:
        """Create a task document in running_tasks folder"""
        running_dir = self._get_running_tasks_dir()
        if not running_dir:
            return None

        doc_path = running_dir / f"{task.task_id}.md"
        content = f"""# Task: {task.description}

**Task ID:** {task.task_id}
**Status:** {task.status.value}
**Created:** {task.created_at.strftime('%Y-%m-%d %H:%M:%S')}

## Task Instructions

{prompt}

## Progress

_Task is running..._
"""
        try:
            with open(doc_path, 'w', encoding='utf-8') as f:
                f.write(content)
            logger.debug(f"Created task document: {doc_path}")
            return doc_path
        except Exception as e:
            logger.error(f"Failed to create task document: {e}")
            return None

    def _update_task_document(
        self,
        task: SubAgentTask,
        result: Optional[str] = None,
        error: Optional[str] = None
    ) -> Optional[Path]:
        """Update task document with result and move to completed_tasks"""
        running_dir = self._get_running_tasks_dir()
        completed_dir = self._get_completed_tasks_dir()
        if not running_dir or not completed_dir:
            return None

        source_path = running_dir / f"{task.task_id}.md"
        if not source_path.exists():
            return None

        # Read existing content
        try:
            with open(source_path, 'r', encoding='utf-8') as f:
                content = f.read()
        except Exception:
            content = ""

        # Update content
        completed_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        status_text = task.status.value

        if result:
            # Truncate result if too long for document
            result_text = result if len(result) <= 5000 else result[:5000] + "\n\n... (truncated)"
            update_content = f"""

## Result

**Completed:** {completed_time}
**Status:** {status_text}

{result_text}
"""
        elif error:
            update_content = f"""

## Error

**Failed:** {completed_time}
**Status:** {status_text}
**Error:** {error}
"""
        else:
            update_content = f"""

## Completed

**Time:** {completed_time}
**Status:** {status_text}
"""

        # Replace progress section or append
        if "## Progress" in content:
            content = content.split("## Progress")[0] + update_content
        else:
            content += update_content

        # Write updated content
        try:
            with open(source_path, 'w', encoding='utf-8') as f:
                f.write(content)
        except Exception as e:
            logger.error(f"Failed to update task document: {e}")

        # Move to completed_tasks
        dest_path = completed_dir / f"{task.task_id}.md"
        try:
            shutil.move(str(source_path), str(dest_path))
            logger.debug(f"Moved task document to: {dest_path}")
            return dest_path
        except Exception as e:
            logger.error(f"Failed to move task document: {e}")
            return source_path

    @property
    def active_task_count(self) -> int:
        """Number of currently running tasks"""
        return sum(
            1 for t in self._tasks.values()
            if t.status in (TaskStatus.PENDING, TaskStatus.RUNNING)
        )

    @property
    def can_create_task(self) -> bool:
        """Check if we can create a new task"""
        return self.active_task_count < self.MAX_SUB_AGENTS

    async def create_task(
        self,
        parent_message_id: str,
        description: str,
        executor: Callable[[SubAgentTask], Awaitable[str]],
        prompt: str = ""
    ) -> Optional[SubAgentTask]:
        """
        Create and start a new Sub Agent task.

        Args:
            parent_message_id: ID of the triggering user message
            description: Task description
            executor: Async function that executes the task
            prompt: Task prompt/instructions (for task document)

        Returns:
            SubAgentTask if created, None if limit reached
        """
        async with self._lock:
            if not self.can_create_task:
                logger.warning(
                    f"User {self.user_id} reached max Sub Agents limit ({self.MAX_SUB_AGENTS})"
                )
                return None

            task_id = str(uuid.uuid4())[:8]
            task = SubAgentTask(
                task_id=task_id,
                parent_message_id=parent_message_id,
                description=description
            )
            self._tasks[task_id] = task

            # Create task document in running_tasks folder
            self._create_task_document(task, prompt)

            # Start the task in background
            async def run_task():
                task.status = TaskStatus.RUNNING

                # Create file tracker to detect files created during execution
                tracker = None
                if self._working_directory and self._send_file_callback:
                    tracker = FileTracker(self._working_directory)
                    tracker.start()

                try:
                    if task.is_cancel_requested():
                        task.status = TaskStatus.CANCELLED
                        self._update_task_document(task, error="Task cancelled")
                        return

                    result = await executor(task)

                    if task.is_cancel_requested():
                        task.status = TaskStatus.CANCELLED
                        self._update_task_document(task, error="Task cancelled")
                    else:
                        # Send any files created during execution
                        files_sent = 0
                        file_paths = []
                        if tracker:
                            try:
                                files_sent, file_paths = await self._send_task_files(tracker)
                            except Exception as e:
                                logger.error(f"Failed to send task files: {e}")

                        # Append file info to result if files were sent
                        if files_sent > 0 and file_paths:
                            file_list = ", ".join(file_paths[:5])
                            if len(file_paths) > 5:
                                file_list += f" (+{len(file_paths) - 5} more)"
                            result = f"{result}\n\n📎 Generated Files ({files_sent}): {file_list}"

                        task.result = result
                        task.status = TaskStatus.COMPLETED
                        logger.info(f"Sub Agent task {task_id} completed (sent {files_sent} files)")

                        # Update and move task document to completed_tasks
                        self._update_task_document(task, result=result)

                        # Notify via callback
                        if self._on_task_complete:
                            try:
                                await self._on_task_complete(task_id, description, result or "Task completed")
                            except Exception as cb_err:
                                logger.error(f"Task complete callback error: {cb_err}")

                except asyncio.CancelledError:
                    task.status = TaskStatus.CANCELLED
                    self._update_task_document(task, error="Task cancelled")
                    logger.info(f"Sub Agent task {task_id} cancelled")
                except Exception as e:
                    task.error = str(e)
                    task.status = TaskStatus.FAILED
                    self._update_task_document(task, error=str(e))
                    logger.error(f"Sub Agent task {task_id} failed: {e}")

                    # Notify failure via callback
                    if self._on_task_complete:
                        try:
                            await self._on_task_complete(task_id, description, f"Task failed: {e}")
                        except Exception as cb_err:
                            logger.error(f"Task complete callback error: {cb_err}")

            task._asyncio_task = asyncio.create_task(run_task())
            logger.info(
                f"User {self.user_id} created Sub Agent task {task_id}: {description[:50]}..."
            )
            return task

    async def create_review_task(
        self,
        parent_message_id: str,
        description: str,
        executor: Callable[[SubAgentTask], Awaitable[str]],
        review_callback: Callable[[str, str, str, str, int], Awaitable[Tuple[bool, str]]],
        send_progress_callback: Callable[[str], Awaitable[None]],
        prompt: str = "",
        review_criteria: str = ""
    ) -> Optional[SubAgentTask]:
        """
        Create a Sub Agent task with automatic quality review and retry mechanism.

        Args:
            parent_message_id: ID of the triggering user message
            description: Task description
            executor: Async function that executes the task
            review_callback: Callback(task_id, description, result, criteria, attempt) -> (passed, feedback)
            send_progress_callback: Callback to send progress updates to user
            prompt: Task prompt/instructions
            review_criteria: Criteria for quality review

        Returns:
            SubAgentTask if created, None if limit reached
        """
        async with self._lock:
            if not self.can_create_task:
                logger.warning(
                    f"User {self.user_id} reached max Sub Agents limit ({self.MAX_SUB_AGENTS})"
                )
                return None

            task_id = str(uuid.uuid4())[:8]
            task = SubAgentTask(
                task_id=task_id,
                parent_message_id=parent_message_id,
                description=description,
                needs_review=True,
                review_criteria=review_criteria,
                original_prompt=prompt
            )
            self._tasks[task_id] = task

            # Create task document in running_tasks folder
            self._create_task_document(task, prompt)

            # Start the task in background with review loop
            async def run_task_with_review():
                task.status = TaskStatus.RUNNING
                max_attempts = task.max_retries

                # Create file tracker (reset at each attempt)
                tracker = None
                if self._working_directory and self._send_file_callback:
                    tracker = FileTracker(self._working_directory)

                # Create review log to track all attempts
                review_log = []

                while task.retry_count < max_attempts:
                    attempt_num = task.retry_count + 1

                    # Reset tracker at start of each attempt
                    if tracker:
                        tracker.start()

                    try:
                        if task.is_cancel_requested():
                            task.status = TaskStatus.CANCELLED
                            self._update_task_document(task, error="Task cancelled")
                            return

                        # Execute the task
                        result = await executor(task)

                        if task.is_cancel_requested():
                            task.status = TaskStatus.CANCELLED
                            self._update_task_document(task, error="Task cancelled")
                            return

                        # Log this attempt (don't send to user yet)
                        attempt_log = {
                            "attempt": attempt_num,
                            "timestamp": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                            "result_preview": result[:2000] if len(result) > 2000 else result,
                        }

                        # Perform quality review
                        suggestions = []
                        missing_dimensions = []
                        try:
                            review_result = await review_callback(
                                task_id, description, result, review_criteria, attempt_num
                            )
                            # Handle both old (2-tuple) and new (4-tuple) callback signatures
                            if isinstance(review_result, tuple):
                                if len(review_result) == 4:
                                    passed, feedback, suggestions, missing_dimensions = review_result
                                else:
                                    passed, feedback = review_result
                                    suggestions, missing_dimensions = [], []
                            else:
                                passed, feedback = review_result, ""
                        except Exception as e:
                            logger.error(f"Review callback failed: {e}")
                            # If review fails, consider it passed to avoid infinite loop
                            passed, feedback = True, ""

                        if passed:
                            # Log successful attempt
                            attempt_log["status"] = "PASSED"
                            attempt_log["feedback"] = feedback
                            review_log.append(attempt_log)

                            # Send any files created during execution
                            files_sent = 0
                            file_paths = []
                            if tracker:
                                try:
                                    files_sent, file_paths = await self._send_task_files(tracker)
                                except Exception as e:
                                    logger.error(f"Failed to send task files: {e}")

                            # Append file info to result if files were sent
                            if files_sent > 0 and file_paths:
                                file_list = ", ".join(file_paths[:5])
                                if len(file_paths) > 5:
                                    file_list += f" (+{len(file_paths) - 5} more)"
                                result = f"{result}\n\n📎 Generated Files ({files_sent}): {file_list}"

                            # Review passed - complete the task
                            task.result = result
                            task.status = TaskStatus.COMPLETED
                            logger.info(f"Sub Agent task {task_id} passed review on attempt {attempt_num} (sent {files_sent} files)")

                            # Update and move task document to completed_tasks
                            self._update_task_document(task, result=result)

                            # Save and send review log file if there were retries
                            if len(review_log) > 1:
                                await self._save_and_send_review_log(task_id, description, review_log)

                            # Send final success notification with summary
                            try:
                                summary = f"✅ Task completed"
                                if len(review_log) > 1:
                                    summary += f" (after {len(review_log)} attempts)"
                                await send_progress_callback(summary)
                            except Exception:
                                pass

                            # Notify via standard callback
                            if self._on_task_complete:
                                try:
                                    await self._on_task_complete(task_id, description, result)
                                except Exception as cb_err:
                                    logger.error(f"Task complete callback error: {cb_err}")
                            return
                        else:
                            # Review failed - log and retry if possible
                            attempt_log["status"] = "REJECTED"
                            attempt_log["feedback"] = feedback
                            attempt_log["suggestions"] = suggestions
                            attempt_log["missing_dimensions"] = missing_dimensions
                            review_log.append(attempt_log)

                            task.add_retry_history(
                                result,
                                feedback,
                                suggestions=suggestions,
                                missing_dimensions=missing_dimensions
                            )
                            task.retry_count += 1

                            if task.retry_count >= max_attempts:
                                # Send any files created during execution
                                files_sent = 0
                                file_paths = []
                                if tracker:
                                    try:
                                        files_sent, file_paths = await self._send_task_files(tracker)
                                    except Exception as e:
                                        logger.error(f"Failed to send task files: {e}")

                                # Append file info to result if files were sent
                                if files_sent > 0 and file_paths:
                                    file_list = ", ".join(file_paths[:5])
                                    if len(file_paths) > 5:
                                        file_list += f" (+{len(file_paths) - 5} more)"
                                    result = f"{result}\n\n📎 Generated Files ({files_sent}): {file_list}"

                                # Max retries reached - send final result anyway
                                task.result = result
                                task.status = TaskStatus.COMPLETED
                                logger.warning(f"Sub Agent task {task_id} reached max retries ({max_attempts}), sent {files_sent} files")

                                self._update_task_document(task, result=result)

                                # Save and send review log
                                await self._save_and_send_review_log(task_id, description, review_log)

                                try:
                                    await send_progress_callback(
                                        f"⚠️ Task completed after {max_attempts} attempts (review log attached)"
                                    )
                                except Exception:
                                    pass

                                if self._on_task_complete:
                                    try:
                                        await self._on_task_complete(task_id, description, result)
                                    except Exception as cb_err:
                                        logger.error(f"Task complete callback error: {cb_err}")
                                return
                            else:
                                # Continue to next iteration silently (no user notification)
                                logger.info(f"Sub Agent task {task_id} failed review, retrying ({task.retry_count}/{max_attempts})")

                    except asyncio.CancelledError:
                        task.status = TaskStatus.CANCELLED
                        self._update_task_document(task, error="Task cancelled")
                        logger.info(f"Sub Agent task {task_id} cancelled during review loop")
                        return
                    except Exception as e:
                        task.error = str(e)
                        task.status = TaskStatus.FAILED
                        self._update_task_document(task, error=str(e))
                        logger.error(f"Sub Agent task {task_id} failed: {e}")

                        try:
                            await send_progress_callback(f"❌ Task execution failed: {str(e)}")
                        except Exception:
                            pass

                        if self._on_task_complete:
                            try:
                                await self._on_task_complete(task_id, description, f"Task failed: {e}")
                            except Exception as cb_err:
                                logger.error(f"Task complete callback error: {cb_err}")
                        return

            task._asyncio_task = asyncio.create_task(run_task_with_review())
            logger.info(
                f"User {self.user_id} created review task {task_id}: {description[:50]}..."
            )
            return task

    async def cancel_tasks_by_parent(self, parent_message_id: str) -> int:
        """
        Cancel all tasks triggered by a specific user message.
        
        Args:
            parent_message_id: The message ID whose tasks should be cancelled
            
        Returns:
            Number of tasks cancelled
        """
        cancelled_count = 0
        async with self._lock:
            for task in self._tasks.values():
                if (task.parent_message_id == parent_message_id and
                    task.status in (TaskStatus.PENDING, TaskStatus.RUNNING)):
                    task.request_cancel()
                    cancelled_count += 1
                    logger.info(f"Cancelled Sub Agent task {task.task_id}")
        return cancelled_count

    async def cancel_all_tasks(self) -> int:
        """Cancel all active tasks"""
        cancelled_count = 0
        async with self._lock:
            for task in self._tasks.values():
                if task.status in (TaskStatus.PENDING, TaskStatus.RUNNING):
                    task.request_cancel()
                    cancelled_count += 1
        return cancelled_count

    def get_completed_results(self, parent_message_id: str) -> List[Dict[str, Any]]:
        """
        Get results from completed tasks for a specific parent message.
        
        Args:
            parent_message_id: The message ID to get results for
            
        Returns:
            List of task results
        """
        results = []
        for task in self._tasks.values():
            if (task.parent_message_id == parent_message_id and
                task.status == TaskStatus.COMPLETED and
                task.result):
                results.append({
                    "task_id": task.task_id,
                    "description": task.description,
                    "result": task.result
                })
        return results

    def get_pending_tasks_for_parent(self, parent_message_id: str) -> List[SubAgentTask]:
        """Get tasks that are still running for a parent message"""
        return [
            task for task in self._tasks.values()
            if (task.parent_message_id == parent_message_id and
                task.status in (TaskStatus.PENDING, TaskStatus.RUNNING))
        ]

    def has_pending_tasks(self, parent_message_id: str) -> bool:
        """Check if there are any pending tasks for a parent message"""
        return len(self.get_pending_tasks_for_parent(parent_message_id)) > 0

    async def wait_for_tasks(
        self,
        parent_message_id: str,
        timeout: float = 300.0
    ) -> List[Dict[str, Any]]:
        """
        Wait for all tasks of a parent message to complete.
        
        Args:
            parent_message_id: The message ID to wait for
            timeout: Maximum wait time in seconds
            
        Returns:
            List of all task results
        """
        start_time = asyncio.get_event_loop().time()
        
        while True:
            pending = self.get_pending_tasks_for_parent(parent_message_id)
            if not pending:
                break
                
            elapsed = asyncio.get_event_loop().time() - start_time
            if elapsed >= timeout:
                logger.warning(
                    f"Timeout waiting for Sub Agent tasks (parent: {parent_message_id})"
                )
                break
            
            # Wait a bit before checking again
            await asyncio.sleep(0.5)
        
        return self.get_completed_results(parent_message_id)

    def cleanup_old_tasks(self, max_age_seconds: float = 3600):
        """Remove old completed/cancelled/failed tasks"""
        now = datetime.now()
        to_remove = []
        for task_id, task in self._tasks.items():
            if task.status in (TaskStatus.COMPLETED, TaskStatus.CANCELLED, TaskStatus.FAILED):
                age = (now - task.created_at).total_seconds()
                if age > max_age_seconds:
                    to_remove.append(task_id)

        for task_id in to_remove:
            del self._tasks[task_id]

        if to_remove:
            logger.debug(f"Cleaned up {len(to_remove)} old tasks for user {self.user_id}")

    def cleanup_old_task_documents(self, max_age_days: int = 7):
        """Remove old task documents from completed_tasks folder"""
        completed_dir = self._get_completed_tasks_dir()
        if not completed_dir or not completed_dir.exists():
            return 0

        now = datetime.now()
        removed_count = 0

        for doc_path in completed_dir.glob("*.md"):
            try:
                # Check file age
                mtime = datetime.fromtimestamp(doc_path.stat().st_mtime)
                age_days = (now - mtime).days
                if age_days > max_age_days:
                    doc_path.unlink()
                    removed_count += 1
            except Exception as e:
                logger.error(f"Failed to cleanup task document {doc_path}: {e}")

        if removed_count > 0:
            logger.debug(f"Cleaned up {removed_count} old task documents for user {self.user_id}")
        return removed_count

    def get_running_task_documents(self) -> List[Path]:
        """Get list of running task documents"""
        running_dir = self._get_running_tasks_dir()
        if not running_dir or not running_dir.exists():
            return []
        return list(running_dir.glob("*.md"))

    def get_completed_task_documents(self, limit: int = 20) -> List[Path]:
        """Get list of recent completed task documents"""
        completed_dir = self._get_completed_tasks_dir()
        if not completed_dir or not completed_dir.exists():
            return []
        docs = list(completed_dir.glob("*.md"))
        # Sort by modification time, newest first
        docs.sort(key=lambda p: p.stat().st_mtime, reverse=True)
        return docs[:limit]

    def get_status_summary(self) -> Dict[str, int]:
        """Get a summary of task statuses"""
        summary = {status.value: 0 for status in TaskStatus}
        for task in self._tasks.values():
            summary[task.status.value] += 1
        return summary

    def get_task(self, task_id: str) -> Optional[SubAgentTask]:
        """Get a specific task by ID"""
        return self._tasks.get(task_id)

    def get_all_tasks(self) -> List[Dict[str, Any]]:
        """Get all tasks with their details"""
        tasks = []
        for task in self._tasks.values():
            task_info = {
                "task_id": task.task_id,
                "description": task.description,
                "status": task.status.value,
                "created_at": task.created_at.strftime('%Y-%m-%d %H:%M:%S'),
            }
            if task.status == TaskStatus.COMPLETED and task.result:
                task_info["result"] = task.result
            elif task.status == TaskStatus.FAILED and task.error:
                task_info["error"] = task.error
            tasks.append(task_info)
        # Sort by created time, newest first
        tasks.sort(key=lambda t: t["created_at"], reverse=True)
        return tasks
