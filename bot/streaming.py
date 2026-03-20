"""Streaming text output by editing the progress (thinking) message."""

import asyncio
import time
import logging

logger = logging.getLogger(__name__)


class DraftStreamer:
    """Streams partial text by editing a Telegram message.

    Instead of sendMessageDraft (which pollutes the input field and can't
    be cleared), this edits the existing thinking/progress message to show
    the streaming text. The message is deleted by the handler when done.

    Resets on each new content block so multi-turn agent responses
    only show the latest turn's text, not accumulated history.
    """

    MIN_INTERVAL = 0.8   # seconds between edits (conservative for editMessage)
    MIN_CHARS = 15        # minimum chars delta before editing

    def __init__(self, thinking_msg):
        """
        Args:
            thinking_msg: The Telegram Message object to edit with streaming text.
        """
        self.thinking_msg = thinking_msg
        self.text = ""           # current content block text
        self.last_sent = ""      # last text successfully sent
        self.last_time = 0.0     # monotonic time of last edit
        self.stopped = False     # stop after agent sends via tool
        self.ever_sent = False   # whether we ever edited the message

    def reset(self):
        """Reset for a new content block / agent turn.

        Clears accumulated text. The progress callback will immediately
        overwrite the thinking_msg with step info, so no explicit edit needed.
        """
        self.text = ""
        self.last_sent = ""

    def stop(self):
        """Stop streaming (agent sent message via tool)."""
        self.stopped = True

    async def append(self, delta: str):
        """Append text delta, edit message if throttle allows."""
        if self.stopped:
            return
        self.text += delta
        now = time.monotonic()
        if (now - self.last_time >= self.MIN_INTERVAL
                and self.text != self.last_sent
                and len(self.text) - len(self.last_sent) >= self.MIN_CHARS):
            await self._send()

    async def flush(self):
        """Force-edit with current accumulated text (no cursor)."""
        if self.stopped:
            return
        if self.text and self.text != self.last_sent:
            # Final flush: no cursor indicator
            try:
                display = self.text[:4000]
                if len(self.text) > 4000:
                    display += "\n..."
                await self.thinking_msg.edit_text(display)
                self.last_sent = self.text
                self.last_time = time.monotonic()
                self.ever_sent = True
            except Exception as e:
                logger.debug(f"Stream flush failed: {e}")

    async def clear(self):
        """No-op. The handler deletes thinking_msg when done."""
        pass

    async def _send(self):
        """Edit the thinking message with current text."""
        try:
            # Truncate to Telegram message limit and add streaming indicator
            display = self.text[:4000]
            if len(self.text) > 4000:
                display += "\n..."
            display += " ▍"  # cursor indicator
            await self.thinking_msg.edit_text(display)
            self.last_sent = self.text
            self.last_time = time.monotonic()
            self.ever_sent = True
        except Exception as e:
            logger.debug(f"Stream edit failed: {e}")
