"""User Message Handler - Non-blocking message processing with Sub Agent support"""

import asyncio
import logging
import uuid
from dataclasses import dataclass, field
from typing import Optional, Callable, Awaitable, Any, Dict, List
from enum import Enum
from datetime import datetime

logger = logging.getLogger(__name__)


class UserState(Enum):
    """User processing state"""
    IDLE = "idle"
    MERGING = "merging"  # In 10-second merge window
    PROCESSING = "processing"  # Main Agent is responding


@dataclass
class PendingMessage:
    """A pending user message"""
    message_id: str
    text: str
    timestamp: datetime = field(default_factory=datetime.now)
    update: Any = None
    context: Any = None
    thinking_msg: Any = None


class NonBlockingMessageHandler:
    """
    Non-blocking message handler for a user.

    Features:
    - 10-second merge window for consecutive messages
    - Main Agent runs in background, doesn't block new messages
    - Buffered messages processed immediately when Main Agent is busy
    - Sub Agent results delivered automatically
    """

    MERGE_WINDOW_SECONDS = 10.0

    def __init__(self, user_id: int, bot: Any = None):
        self.user_id = user_id
        self.bot = bot  # For sending notifications
        self._state = UserState.IDLE
        self._lock = asyncio.Lock()

        # Current processing
        self._current_message: Optional[PendingMessage] = None
        self._window_task: Optional[asyncio.Task] = None
        self._processing_task: Optional[asyncio.Task] = None
        self._cancel_requested = asyncio.Event()

        # Message queue for when Main Agent is busy
        self._message_queue: asyncio.Queue = asyncio.Queue()
        self._queue_processor_task: Optional[asyncio.Task] = None

        # Callbacks
        self._process_func: Optional[Callable] = None
        self._send_progress_func: Optional[Callable] = None

    @property
    def is_busy(self) -> bool:
        return self._state != UserState.IDLE

    async def handle_message(
        self,
        text: str,
        update: Any,
        context: Any,
        process_func: Callable[[str, Any, Any, Any], Awaitable[None]],
        send_progress: Callable[[], Awaitable[Any]]
    ) -> None:
        """
        Handle incoming message - non-blocking.

        Returns immediately after queuing/starting the message.
        """
        self._process_func = process_func
        self._send_progress_func = send_progress

        async with self._lock:
            if self._state == UserState.IDLE:
                # Start merge window
                await self._start_merge_window(text, update, context)
            elif self._state == UserState.MERGING:
                # Within merge window - merge messages
                await self._merge_message(text)
            elif self._state == UserState.PROCESSING:
                # Main Agent is busy - queue the message
                await self._queue_message(text, update, context)

    async def _start_merge_window(self, text: str, update: Any, context: Any) -> None:
        """Start the 10-second merge window"""
        self._state = UserState.MERGING
        self._cancel_requested.clear()

        # Send "thinking" indicator
        thinking_msg = await self._send_progress_func()

        self._current_message = PendingMessage(
            message_id=str(uuid.uuid4())[:8],
            text=text,
            update=update,
            context=context,
            thinking_msg=thinking_msg
        )

        logger.info(f"User {self.user_id}: Starting merge window")

        # Start merge window timer
        self._window_task = asyncio.create_task(self._merge_window_timer())

    async def _merge_window_timer(self) -> None:
        """Timer for merge window - when it expires, start processing"""
        try:
            await asyncio.sleep(self.MERGE_WINDOW_SECONDS)

            async with self._lock:
                if self._state == UserState.MERGING and self._current_message:
                    # Window expired, start processing
                    self._state = UserState.PROCESSING
                    logger.info(f"User {self.user_id}: Merge window expired, starting processing")

                    # Start processing in background (non-blocking)
                    self._processing_task = asyncio.create_task(
                        self._run_processing()
                    )
        except asyncio.CancelledError:
            pass

    async def _merge_message(self, new_text: str) -> None:
        """Merge new message with current pending message"""
        if self._current_message:
            self._current_message.text += f"\n{new_text}"
            logger.info(f"User {self.user_id}: Merged message")

            # Reset the merge window timer
            if self._window_task and not self._window_task.done():
                self._window_task.cancel()
                try:
                    await self._window_task
                except asyncio.CancelledError:
                    pass

            # Restart timer
            self._window_task = asyncio.create_task(self._merge_window_timer())

    async def _queue_message(self, text: str, update: Any, context: Any) -> None:
        """Queue a message for later processing"""
        await self._message_queue.put({
            'text': text,
            'update': update,
            'context': context
        })
        logger.info(f"User {self.user_id}: Message queued (queue size: {self._message_queue.qsize()})")

        # Notify user that message was queued
        try:
            from ..i18n import t
            await update.message.reply_text(f"📥 {t('AGENT_BUSY')}")
        except Exception as e:
            logger.warning(f"Failed to send queue notification: {e}")

        # Start queue processor if not running
        if self._queue_processor_task is None or self._queue_processor_task.done():
            self._queue_processor_task = asyncio.create_task(self._process_queue())

    async def _run_processing(self) -> None:
        """Run Main Agent processing in background"""
        try:
            msg = self._current_message
            if msg and self._process_func:
                await self._process_func(msg.text, msg.update, msg.context, msg.thinking_msg)
        except asyncio.CancelledError:
            logger.debug(f"User {self.user_id}: Processing cancelled")
        except Exception as e:
            logger.error(f"User {self.user_id}: Processing error: {e}")
        finally:
            async with self._lock:
                self._state = UserState.IDLE
                self._current_message = None
                logger.info(f"User {self.user_id}: Processing finished, state is IDLE")

            # Check if there are queued messages
            if not self._message_queue.empty():
                logger.info(f"User {self.user_id}: Processing queued messages")
                asyncio.create_task(self._process_queue())

    async def _process_queue(self) -> None:
        """Process queued messages - merge all queued messages into one"""
        async with self._lock:
            if self._state != UserState.IDLE:
                return
            if self._message_queue.empty():
                return

        # Drain all queued messages and merge them
        merged_texts = []
        first_update = None
        first_context = None

        while not self._message_queue.empty():
            try:
                msg_data = self._message_queue.get_nowait()
                merged_texts.append(msg_data['text'])
                if first_update is None:
                    first_update = msg_data['update']
                    first_context = msg_data['context']
            except asyncio.QueueEmpty:
                break

        if merged_texts and first_update:
            merged_text = "\n".join(merged_texts)
            logger.info(f"User {self.user_id}: Merged {len(merged_texts)} queued messages")

            async with self._lock:
                if self._state == UserState.IDLE:
                    await self._start_merge_window(
                        merged_text,
                        first_update,
                        first_context
                    )

    def cancel_current(self) -> None:
        """Cancel current processing"""
        self._cancel_requested.set()
        if self._window_task and not self._window_task.done():
            self._window_task.cancel()
        if self._processing_task and not self._processing_task.done():
            self._processing_task.cancel()

    def is_cancelled(self) -> bool:
        return self._cancel_requested.is_set()


# Backwards compatible class name
UserMessageHandler = NonBlockingMessageHandler


# Global registry of message handlers per user
_handlers: Dict[int, NonBlockingMessageHandler] = {}
_handlers_lock = asyncio.Lock()


async def get_message_handler(user_id: int, bot: Any = None) -> NonBlockingMessageHandler:
    """Get or create a message handler for a user"""
    async with _handlers_lock:
        if user_id not in _handlers:
            _handlers[user_id] = NonBlockingMessageHandler(user_id, bot)
        elif bot and not _handlers[user_id].bot:
            _handlers[user_id].bot = bot
        return _handlers[user_id]
