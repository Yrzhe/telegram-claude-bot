"""Streaming draft messages to Telegram via sendMessageDraft API."""

import time
import logging

logger = logging.getLogger(__name__)


class DraftStreamer:
    """Streams partial text to Telegram via sendMessageDraft.

    Resets on each new content block so multi-turn agent responses
    only show the latest turn's text, not accumulated history.
    """

    MIN_INTERVAL = 0.4   # seconds between API calls
    DRAFT_ID = 1          # fixed non-zero ID (same ID = animated update)

    def __init__(self, bot, chat_id):
        self.bot = bot
        self.chat_id = chat_id
        self.text = ""           # current content block text
        self.last_sent = ""      # last text successfully sent
        self.last_time = 0.0     # monotonic time of last send

    def reset(self):
        """Reset for a new content block / agent turn."""
        self.text = ""
        self.last_sent = ""

    async def append(self, delta: str):
        """Append text delta, send draft if throttle allows."""
        self.text += delta
        now = time.monotonic()
        if (now - self.last_time >= self.MIN_INTERVAL
                and self.text != self.last_sent
                and len(self.text) - len(self.last_sent) >= 5):
            await self._send()

    async def flush(self):
        """Force-send current accumulated text."""
        if self.text and self.text != self.last_sent:
            await self._send()

    async def _send(self):
        """Call sendMessageDraft via do_api_request."""
        try:
            await self.bot.do_api_request(
                "sendMessageDraft",
                api_kwargs={
                    "chat_id": self.chat_id,
                    "draft_id": self.DRAFT_ID,
                    "text": self.text[:4096],
                },
            )
            self.last_sent = self.text
            self.last_time = time.monotonic()
        except Exception as e:
            logger.debug(f"Draft send failed: {e}")
            # Non-fatal: draft is optional UX enhancement
