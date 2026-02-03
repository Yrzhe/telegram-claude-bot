"""Message queue for serializing Telegram messages to ensure correct ordering."""

import asyncio
import logging
from typing import Any, Callable, Awaitable, Dict, Optional
from dataclasses import dataclass
from enum import Enum

from .agent.tools import convert_to_markdown_v2

logger = logging.getLogger(__name__)


class MessageType(Enum):
    TEXT = "text"
    FILE = "file"


@dataclass
class QueuedMessage:
    """A message waiting to be sent."""
    msg_type: MessageType
    # For TEXT: text content; For FILE: file path
    content: str
    # For FILE: optional caption
    caption: Optional[str] = None


class UserMessageQueue:
    """
    Per-user message queue that ensures messages are sent in order.

    Messages are queued and sent one at a time, waiting for each
    to complete before sending the next. This prevents race conditions
    where Telegram might deliver messages out of order.
    """

    def __init__(
        self,
        user_id: int,
        raw_send_message: Callable[[int, str], Awaitable[None]],
        raw_send_file: Callable[[int, str, Optional[str]], Awaitable[bool]]
    ):
        self.user_id = user_id
        self._raw_send_message = raw_send_message
        self._raw_send_file = raw_send_file
        self._queue: asyncio.Queue[QueuedMessage] = asyncio.Queue()
        self._processing = False
        self._lock = asyncio.Lock()

    async def send_message(self, text: str) -> None:
        """Queue a text message to be sent."""
        msg = QueuedMessage(msg_type=MessageType.TEXT, content=text)
        await self._queue.put(msg)
        await self._ensure_processing()

    async def send_file(self, file_path: str, caption: Optional[str] = None) -> bool:
        """Queue a file to be sent. Returns True when successfully queued."""
        msg = QueuedMessage(msg_type=MessageType.FILE, content=file_path, caption=caption)
        await self._queue.put(msg)
        await self._ensure_processing()
        return True  # Queued successfully; actual send result not returned immediately

    async def _ensure_processing(self) -> None:
        """Start processing the queue if not already running."""
        async with self._lock:
            if not self._processing:
                self._processing = True
                asyncio.create_task(self._process_queue())

    async def _process_queue(self) -> None:
        """Process queued messages one at a time."""
        try:
            while True:
                try:
                    # Wait for a message with timeout
                    msg = await asyncio.wait_for(self._queue.get(), timeout=0.1)
                except asyncio.TimeoutError:
                    # Check if queue is empty
                    if self._queue.empty():
                        break
                    continue

                try:
                    if msg.msg_type == MessageType.TEXT:
                        await self._send_text(msg.content)
                    elif msg.msg_type == MessageType.FILE:
                        await self._raw_send_file(self.user_id, msg.content, msg.caption)
                except Exception as e:
                    logger.error(f"Failed to send message to user {self.user_id}: {e}")
                finally:
                    self._queue.task_done()
        finally:
            async with self._lock:
                self._processing = False
                # Check if new messages arrived while we were stopping
                if not self._queue.empty():
                    self._processing = True
                    asyncio.create_task(self._process_queue())

    async def _send_text(self, text: str) -> None:
        """Send text message, splitting if too long."""
        if len(text) > 4000:
            for i in range(0, len(text), 4000):
                await self._raw_send_message(self.user_id, text[i:i+4000])
        else:
            await self._raw_send_message(self.user_id, text)

    async def flush(self) -> None:
        """Wait for all queued messages to be sent."""
        await self._queue.join()


class MessageQueueManager:
    """
    Manages per-user message queues.

    Usage:
        manager = MessageQueueManager(bot)

        # Get queue-wrapped callbacks for a user
        send_msg, send_file = manager.get_callbacks(user_id)

        # These are now serialized
        await send_msg("Hello")
        await send_file("file.pdf", "Here's your file")
    """

    def __init__(self, bot: Any):
        self.bot = bot
        self._queues: Dict[int, UserMessageQueue] = {}
        self._lock = asyncio.Lock()

    async def _raw_send_message(self, user_id: int, text: str) -> None:
        """Raw message send (directly to Telegram) with MarkdownV2 support."""
        formatted_text = convert_to_markdown_v2(text)
        try:
            await self.bot.send_message(chat_id=user_id, text=formatted_text, parse_mode="MarkdownV2")
        except Exception as e:
            # Fallback to plain text if MarkdownV2 parsing fails
            logger.debug(f"MarkdownV2 parse failed for user {user_id}, falling back to plain text: {e}")
            await self.bot.send_message(chat_id=user_id, text=text)

    async def _raw_send_file(self, user_id: int, file_path: str, caption: Optional[str]) -> bool:
        """Raw file send (directly to Telegram). Returns False if file not found."""
        from pathlib import Path

        path = Path(file_path)
        if not path.exists() or not path.is_file():
            logger.warning(f"File not found for user {user_id}: {file_path}")
            return False

        # Check file size (50MB limit for Telegram)
        if path.stat().st_size > 50 * 1024 * 1024:
            await self.bot.send_message(chat_id=user_id, text="File too large (>50MB)")
            return False

        try:
            await self.bot.send_document(
                chat_id=user_id,
                document=open(path, 'rb'),
                caption=caption
            )
            logger.info(f"File sent to user {user_id}: {file_path}")
            return True
        except Exception as e:
            logger.error(f"Failed to send file to user {user_id}: {file_path}, error: {e}")
            return False

    async def get_queue(self, user_id: int) -> UserMessageQueue:
        """Get or create a message queue for a user."""
        async with self._lock:
            if user_id not in self._queues:
                self._queues[user_id] = UserMessageQueue(
                    user_id=user_id,
                    raw_send_message=self._raw_send_message,
                    raw_send_file=self._raw_send_file
                )
            return self._queues[user_id]

    def get_callbacks(self, user_id: int, user_data_path: Any = None) -> tuple[
        Callable[[str], Awaitable[None]],
        Callable[[str, Optional[str]], Awaitable[bool]]
    ]:
        """
        Get queue-wrapped send_message and send_file callbacks for a user.

        Args:
            user_id: Telegram user ID
            user_data_path: Path to user's data directory (for file resolution)

        Returns:
            (send_message, send_file) callback tuple
        """
        from pathlib import Path

        async def send_message(text: str) -> None:
            queue = await self.get_queue(user_id)
            await queue.send_message(text)

        async def send_file(file_path: str, caption: Optional[str] = None) -> bool:
            """Send file with path resolution."""
            # Build list of candidate paths to try
            candidates = []
            file_path_obj = Path(file_path)

            if user_data_path:
                user_path = Path(user_data_path)
                # 1. Try as provided (relative to user_data_path)
                candidates.append(user_path / file_path)

                # 2. Try just the filename in user_data_path root
                if file_path_obj.name != file_path:
                    candidates.append(user_path / file_path_obj.name)

                # 3. Search common subdirectories for the filename
                common_subdirs = ['reports', 'analysis', 'documents', 'uploads', 'output']
                for subdir in common_subdirs:
                    subdir_path = user_path / subdir
                    if subdir_path.exists():
                        candidates.append(subdir_path / file_path_obj.name)
                        if file_path_obj.name != file_path:
                            candidates.append(subdir_path / file_path)

            # 4. If absolute path, try directly
            if file_path_obj.is_absolute():
                candidates.append(file_path_obj)

            # Find first existing file
            full_path = None
            for candidate in candidates:
                if candidate and candidate.exists() and candidate.is_file():
                    full_path = str(candidate)
                    break

            if not full_path:
                logger.warning(f"File not found for user {user_id}: {file_path}")
                return False

            queue = await self.get_queue(user_id)
            await queue.send_file(full_path, caption)
            return True

        return send_message, send_file

    async def flush_user(self, user_id: int) -> None:
        """Wait for all messages in a user's queue to be sent."""
        async with self._lock:
            if user_id in self._queues:
                await self._queues[user_id].flush()

    async def flush_all(self) -> None:
        """Wait for all queues to be flushed."""
        async with self._lock:
            queues = list(self._queues.values())
        for queue in queues:
            await queue.flush()
