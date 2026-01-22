"""File Tracker - Tracks new/modified files during task execution"""

import logging
import time
import tempfile
import zipfile
from pathlib import Path
from typing import Callable, Awaitable, Optional

logger = logging.getLogger(__name__)

# File extensions to exclude
EXCLUDED_EXTENSIONS = {
    '.tmp', '.log', '.pyc', '.pyo', '.swp', '.swo',
    '.DS_Store', '.gitignore'
}

# Directories to exclude
EXCLUDED_DIRS = {
    '__pycache__', '.git', 'node_modules', '.venv',
    '.cache', '.pytest_cache', '.mypy_cache', 'venv',
    'schedules'  # Don't send schedule config changes
}

# Max files before zipping
MAX_FILES_BEFORE_ZIP = 5


class FileTracker:
    """
    Tracks file changes during task execution.

    Usage:
        tracker = FileTracker(working_directory)
        tracker.start()
        # ... task execution ...
        new_files = tracker.get_new_files()
    """

    def __init__(self, working_directory: Path):
        """
        Initialize FileTracker.

        Args:
            working_directory: The directory to track
        """
        self.working_dir = Path(working_directory).resolve()
        self.start_time: Optional[float] = None
        self.initial_files: dict[Path, float] = {}  # {path: mtime}

    def start(self):
        """Record initial file state before task execution"""
        self.start_time = time.time()
        self.initial_files = self._scan_files()
        logger.debug(f"FileTracker started, tracking {len(self.initial_files)} files")

    def _scan_files(self) -> dict[Path, float]:
        """Scan all files in working directory and return {path: mtime}"""
        files = {}
        try:
            for path in self.working_dir.rglob('*'):
                if path.is_file() and not self._should_exclude(path):
                    try:
                        files[path] = path.stat().st_mtime
                    except (OSError, PermissionError):
                        pass
        except Exception as e:
            logger.error(f"Error scanning files: {e}")
        return files

    def _should_exclude(self, path: Path) -> bool:
        """Check if a file should be excluded from tracking"""
        # Check extension
        if path.suffix.lower() in EXCLUDED_EXTENSIONS:
            return True

        # Check if in excluded directory
        for part in path.relative_to(self.working_dir).parts:
            if part in EXCLUDED_DIRS:
                return True

        # Check hidden files (starting with .)
        if path.name.startswith('.'):
            return True

        # Check temp files (starting with ~)
        if path.name.startswith('~'):
            return True

        return False

    def get_new_files(self) -> list[Path]:
        """
        Get list of new/modified files since start() was called.

        Returns:
            List of Path objects for new/modified files
        """
        if self.start_time is None:
            logger.warning("FileTracker.start() was not called")
            return []

        current_files = self._scan_files()
        new_files = []

        for path, mtime in current_files.items():
            # New file or modified file
            if path not in self.initial_files:
                new_files.append(path)
                logger.debug(f"New file detected: {path}")
            elif mtime > self.initial_files[path]:
                new_files.append(path)
                logger.debug(f"Modified file detected: {path}")

        # Sort by modification time (newest first)
        new_files.sort(key=lambda p: p.stat().st_mtime, reverse=True)

        logger.info(f"FileTracker found {len(new_files)} new/modified files")
        return new_files


async def send_tracked_files(
    files: list[Path],
    working_dir: Path,
    send_file_callback: Callable[[str, Optional[str]], Awaitable[bool]],
    send_message_callback: Callable[[str], Awaitable[None]] | None = None
) -> int:
    """
    Send tracked files to user.

    Args:
        files: List of file paths to send
        working_dir: Working directory (for relative path calculation)
        send_file_callback: Callback to send a file
        send_message_callback: Optional callback to send a message

    Returns:
        Number of files successfully sent
    """
    if not files:
        return 0

    sent_count = 0
    working_dir = Path(working_dir).resolve()

    # Filter out files that no longer exist
    existing_files = [f for f in files if f.exists()]
    if not existing_files:
        return 0

    if len(existing_files) <= MAX_FILES_BEFORE_ZIP:
        # Send files individually
        for file_path in existing_files:
            try:
                rel_path = file_path.relative_to(working_dir)
                caption = f"📎 {rel_path}"
                success = await send_file_callback(str(file_path), caption)
                if success:
                    sent_count += 1
                    logger.debug(f"Sent file: {rel_path}")
            except Exception as e:
                logger.error(f"Failed to send file {file_path}: {e}")
    else:
        # Create zip and send
        try:
            # Create zip in system temp directory (not user's working dir)
            with tempfile.NamedTemporaryFile(
                suffix='.zip',
                prefix='task_files_',
                delete=False
            ) as tmp_file:
                zip_path = Path(tmp_file.name)

            # Create zip file
            with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                for file_path in existing_files:
                    try:
                        arcname = file_path.relative_to(working_dir)
                        zipf.write(file_path, arcname)
                    except Exception as e:
                        logger.error(f"Failed to add file to zip: {file_path}, {e}")

            # Send zip
            caption = f"📦 任务生成的 {len(existing_files)} 个文件"
            success = await send_file_callback(str(zip_path), caption)

            if success:
                sent_count = len(existing_files)
                logger.info(f"Sent {len(existing_files)} files as zip")

            # Delete zip file immediately after sending
            try:
                zip_path.unlink()
                logger.debug(f"Deleted temporary zip: {zip_path}")
            except Exception as e:
                logger.warning(f"Failed to delete temp zip: {e}")

        except Exception as e:
            logger.error(f"Failed to create/send zip: {e}")
            # Fallback: try to send first few files individually
            if send_message_callback:
                await send_message_callback(f"⚠️ 打包文件失败，尝试单独发送前 {MAX_FILES_BEFORE_ZIP} 个文件")
            for file_path in existing_files[:MAX_FILES_BEFORE_ZIP]:
                try:
                    rel_path = file_path.relative_to(working_dir)
                    success = await send_file_callback(str(file_path), f"📎 {rel_path}")
                    if success:
                        sent_count += 1
                except Exception:
                    pass

    return sent_count
