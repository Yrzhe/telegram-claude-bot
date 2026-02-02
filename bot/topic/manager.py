"""Topic Manager - Core implementation for dynamic topic-based context management"""

import json
import logging
import time
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Optional

from .classifier import (
    TopicClassifier,
    ClassificationResult,
    ClassificationAction,
    extract_keywords_simple
)

logger = logging.getLogger(__name__)


class TopicStatus(str, Enum):
    """Topic lifecycle status"""
    ACTIVE = "active"  # Currently in active context
    RECENT = "recent"  # Recently used, summary available
    ARCHIVED = "archived"  # Summarized and offloaded


@dataclass
class Topic:
    """Represents a conversation topic"""
    id: str
    title: str
    status: TopicStatus = TopicStatus.ACTIVE
    keywords: list[str] = field(default_factory=list)
    summary: str = ""  # Generated when topic is archived
    message_count: int = 0
    first_seen: float = field(default_factory=time.time)
    last_active: float = field(default_factory=time.time)
    # Token tracking (estimated)
    estimated_tokens: int = 0

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization"""
        return {
            "id": self.id,
            "title": self.title,
            "status": self.status.value,
            "keywords": self.keywords,
            "summary": self.summary,
            "message_count": self.message_count,
            "first_seen": self.first_seen,
            "last_active": self.last_active,
            "estimated_tokens": self.estimated_tokens
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Topic":
        """Create from dictionary"""
        return cls(
            id=data["id"],
            title=data["title"],
            status=TopicStatus(data.get("status", "active")),
            keywords=data.get("keywords", []),
            summary=data.get("summary", ""),
            message_count=data.get("message_count", 0),
            first_seen=data.get("first_seen", time.time()),
            last_active=data.get("last_active", time.time()),
            estimated_tokens=data.get("estimated_tokens", 0)
        )

    def touch(self, tokens_delta: int = 0):
        """Update last active time and optionally add tokens"""
        self.last_active = time.time()
        self.message_count += 1
        self.estimated_tokens += tokens_delta

    def is_stale(self, timeout_seconds: int = 7200) -> bool:
        """Check if topic has been inactive for too long"""
        return time.time() - self.last_active > timeout_seconds


@dataclass
class TopicContext:
    """Context string to inject into system prompt"""
    current_topic: Optional[str] = None  # Full topic details
    recent_topics: str = ""  # Summaries of recent topics
    archived_topics: str = ""  # Just titles for recall
    total_topics: int = 0
    active_topics: int = 0


class TopicManager:
    """
    Manages conversation topics for a user.

    Provides:
    - Topic detection and classification
    - Context building for system prompt
    - Auto-archival and compaction
    - Topic recall
    """

    # Configuration
    MAX_ACTIVE_TOPICS = 5
    ARCHIVE_TIMEOUT_SECONDS = 7200  # 2 hours
    SOFT_TOKEN_LIMIT = 100000
    HARD_TOKEN_LIMIT = 140000

    def __init__(
        self,
        user_directory: str | Path,
        api_key: str = "",
        base_url: Optional[str] = None
    ):
        """
        Initialize TopicManager.

        Args:
            user_directory: User's data directory
            api_key: Anthropic API key (for Haiku classification)
            base_url: Optional API base URL
        """
        self.user_dir = Path(user_directory)
        self.topics_file = self.user_dir / "topics.json"
        self.api_key = api_key
        self.base_url = base_url

        # State
        self.topics: dict[str, Topic] = {}
        self.active_topic_ids: list[str] = []  # Ordered by recency
        self.current_topic_id: Optional[str] = None

        # Classifier
        self.classifier = TopicClassifier(api_key, base_url)

        # Load existing topics
        self._load_topics()

    def _load_topics(self):
        """Load topics from file"""
        if self.topics_file.exists():
            try:
                data = json.loads(self.topics_file.read_text(encoding='utf-8'))
                self.active_topic_ids = data.get("active_topic_ids", [])
                self.current_topic_id = data.get("current_topic_id")

                topics_data = data.get("topics", {})
                for topic_id, topic_dict in topics_data.items():
                    self.topics[topic_id] = Topic.from_dict(topic_dict)

                logger.info(f"Loaded {len(self.topics)} topics, {len(self.active_topic_ids)} active")
            except Exception as e:
                logger.error(f"Failed to load topics: {e}")

    def _save_topics(self):
        """Save topics to file"""
        try:
            self.user_dir.mkdir(parents=True, exist_ok=True)
            data = {
                "active_topic_ids": self.active_topic_ids,
                "current_topic_id": self.current_topic_id,
                "topics": {tid: t.to_dict() for tid, t in self.topics.items()}
            }
            self.topics_file.write_text(
                json.dumps(data, indent=2, ensure_ascii=False),
                encoding='utf-8'
            )
        except Exception as e:
            logger.error(f"Failed to save topics: {e}")

    def _generate_topic_id(self) -> str:
        """Generate a unique topic ID"""
        date_str = datetime.now().strftime("%Y%m%d")
        short_uuid = str(uuid.uuid4())[:8]
        return f"topic_{date_str}_{short_uuid}"

    async def classify_message(self, message: str) -> ClassificationResult:
        """
        Classify a user message.

        Args:
            message: User message

        Returns:
            ClassificationResult with action and metadata
        """
        current_topic = None
        if self.current_topic_id and self.current_topic_id in self.topics:
            t = self.topics[self.current_topic_id]
            current_topic = {"title": t.title, "keywords": t.keywords}

        recent_topics = []
        for tid in self.active_topic_ids:
            if tid != self.current_topic_id and tid in self.topics:
                t = self.topics[tid]
                recent_topics.append({"title": t.title, "summary": t.summary})

        archived_topics = []
        for tid, t in self.topics.items():
            if t.status == TopicStatus.ARCHIVED:
                archived_topics.append({"title": t.title, "id": tid})

        return await self.classifier.classify(
            message,
            current_topic,
            recent_topics,
            archived_topics
        )

    def create_topic(self, title: str, keywords: list[str] = None) -> Topic:
        """
        Create a new topic.

        Args:
            title: Topic title
            keywords: Initial keywords

        Returns:
            Created Topic
        """
        topic_id = self._generate_topic_id()
        topic = Topic(
            id=topic_id,
            title=title,
            keywords=keywords or [],
            status=TopicStatus.ACTIVE
        )

        self.topics[topic_id] = topic
        self.active_topic_ids.insert(0, topic_id)
        self.current_topic_id = topic_id

        # Enforce max active topics
        while len(self.active_topic_ids) > self.MAX_ACTIVE_TOPICS:
            old_id = self.active_topic_ids.pop()
            self._archive_topic(old_id)

        self._save_topics()
        logger.info(f"Created topic: {title} ({topic_id})")
        return topic

    def update_current_topic(self, tokens_delta: int = 0):
        """Update the current topic's activity"""
        if self.current_topic_id and self.current_topic_id in self.topics:
            self.topics[self.current_topic_id].touch(tokens_delta)
            self._save_topics()

    def switch_topic(self, topic_id: str) -> Optional[Topic]:
        """
        Switch to an existing topic.

        Args:
            topic_id: Topic ID to switch to

        Returns:
            Topic if found, None otherwise
        """
        if topic_id not in self.topics:
            return None

        topic = self.topics[topic_id]

        # If archived, recall it
        if topic.status == TopicStatus.ARCHIVED:
            self._recall_topic(topic_id)

        # Move to front of active list
        if topic_id in self.active_topic_ids:
            self.active_topic_ids.remove(topic_id)
        self.active_topic_ids.insert(0, topic_id)
        self.current_topic_id = topic_id
        topic.touch()

        self._save_topics()
        logger.info(f"Switched to topic: {topic.title}")
        return topic

    def recall_topic_by_name(self, name: str) -> Optional[Topic]:
        """
        Recall a topic by partial name match.

        Args:
            name: Topic name to search for

        Returns:
            Topic if found, None otherwise
        """
        name_lower = name.lower()
        for tid, topic in self.topics.items():
            if name_lower in topic.title.lower():
                return self.switch_topic(tid)
        return None

    def _archive_topic(self, topic_id: str):
        """Archive a topic (internal)"""
        if topic_id not in self.topics:
            return

        topic = self.topics[topic_id]
        topic.status = TopicStatus.ARCHIVED

        # Generate summary if not already present
        if not topic.summary:
            topic.summary = f"Topic about {topic.title} with {topic.message_count} messages"

        if topic_id in self.active_topic_ids:
            self.active_topic_ids.remove(topic_id)

        if self.current_topic_id == topic_id:
            self.current_topic_id = self.active_topic_ids[0] if self.active_topic_ids else None

        logger.info(f"Archived topic: {topic.title}")

    def _recall_topic(self, topic_id: str):
        """Recall an archived topic (internal)"""
        if topic_id not in self.topics:
            return

        topic = self.topics[topic_id]
        topic.status = TopicStatus.ACTIVE
        topic.touch()

        logger.info(f"Recalled topic: {topic.title}")

    async def generate_topic_summary(self, topic_id: str) -> str:
        """
        Generate a summary for a topic using Haiku.

        Args:
            topic_id: Topic ID

        Returns:
            Generated summary
        """
        if topic_id not in self.topics:
            return ""

        topic = self.topics[topic_id]

        if not self.api_key:
            # Simple fallback summary
            return f"Discussed {topic.title}. Keywords: {', '.join(topic.keywords[:5])}"

        try:
            import anthropic

            client_args = {"api_key": self.api_key}
            if self.base_url:
                client_args["base_url"] = self.base_url

            client = anthropic.Anthropic(**client_args)

            prompt = f"""Summarize this conversation topic in 1-2 sentences:

Topic: {topic.title}
Keywords: {', '.join(topic.keywords)}
Message count: {topic.message_count}

Keep the summary concise and capture the key points discussed."""

            response = client.messages.create(
                model="claude-3-5-haiku-20241022",
                max_tokens=100,
                messages=[{"role": "user", "content": prompt}]
            )

            summary = response.content[0].text.strip()
            topic.summary = summary
            self._save_topics()
            return summary

        except Exception as e:
            logger.error(f"Failed to generate summary: {e}")
            return f"Discussed {topic.title}"

    async def auto_maintenance(self, current_tokens: int = 0):
        """
        Perform automatic maintenance based on token count and topic staleness.

        Args:
            current_tokens: Current total token count in session
        """
        now = time.time()
        archived_count = 0

        # Check for stale topics
        for topic_id in list(self.active_topic_ids):
            if topic_id not in self.topics:
                self.active_topic_ids.remove(topic_id)
                continue

            topic = self.topics[topic_id]

            # Archive stale topics based on token pressure
            if current_tokens >= self.HARD_TOKEN_LIMIT:
                # Hard limit - archive all except current
                if topic_id != self.current_topic_id:
                    await self.generate_topic_summary(topic_id)
                    self._archive_topic(topic_id)
                    archived_count += 1

            elif current_tokens >= self.SOFT_TOKEN_LIMIT:
                # Soft limit - archive topics inactive > 1 hour
                if topic.is_stale(3600) and topic_id != self.current_topic_id:
                    await self.generate_topic_summary(topic_id)
                    self._archive_topic(topic_id)
                    archived_count += 1

            else:
                # Normal - archive topics inactive > 2 hours
                if topic.is_stale(self.ARCHIVE_TIMEOUT_SECONDS) and topic_id != self.current_topic_id:
                    await self.generate_topic_summary(topic_id)
                    self._archive_topic(topic_id)
                    archived_count += 1

        if archived_count > 0:
            logger.info(f"Auto-maintenance archived {archived_count} topics")
            self._save_topics()

    def get_context_for_prompt(self) -> TopicContext:
        """
        Build topic context string for system prompt injection.

        Returns:
            TopicContext with formatted strings
        """
        context = TopicContext(
            total_topics=len(self.topics),
            active_topics=len(self.active_topic_ids)
        )

        # Current topic (full details)
        if self.current_topic_id and self.current_topic_id in self.topics:
            topic = self.topics[self.current_topic_id]
            context.current_topic = (
                f"**Current Topic**: {topic.title}\n"
                f"- Keywords: {', '.join(topic.keywords[:5]) if topic.keywords else 'None'}\n"
                f"- Messages: {topic.message_count}"
            )

        # Recent topics (summaries)
        recent_lines = []
        for tid in self.active_topic_ids:
            if tid != self.current_topic_id and tid in self.topics:
                t = self.topics[tid]
                if t.summary:
                    recent_lines.append(f"- {t.title}: {t.summary}")
                else:
                    recent_lines.append(f"- {t.title} ({t.message_count} messages)")

        if recent_lines:
            context.recent_topics = "**Recent Topics**:\n" + "\n".join(recent_lines)

        # Archived topics (just titles for recall)
        archived_titles = []
        for tid, t in self.topics.items():
            if t.status == TopicStatus.ARCHIVED:
                archived_titles.append(t.title)

        if archived_titles:
            context.archived_topics = (
                f"**Archived Topics** (can be recalled if user mentions): "
                f"{', '.join(archived_titles[:10])}"
            )

        return context

    def get_context_string(self) -> str:
        """
        Get formatted context string for system prompt.

        Returns:
            Formatted topic context string
        """
        ctx = self.get_context_for_prompt()
        parts = []

        if ctx.current_topic:
            parts.append(ctx.current_topic)
        if ctx.recent_topics:
            parts.append(ctx.recent_topics)
        if ctx.archived_topics:
            parts.append(ctx.archived_topics)

        if not parts:
            return ""

        return "## Conversation Topics\n\n" + "\n\n".join(parts)

    async def process_message(
        self,
        message: str,
        tokens_estimate: int = 0
    ) -> tuple[Topic, ClassificationResult]:
        """
        Process a message: classify and update topic state.

        Args:
            message: User message
            tokens_estimate: Estimated tokens for this exchange

        Returns:
            Tuple of (active Topic, ClassificationResult)
        """
        # Classify the message
        result = await self.classify_message(message)

        if result.action == ClassificationAction.NEW:
            # Create new topic
            title = result.new_title or "New conversation"
            keywords = result.keywords or extract_keywords_simple(message)
            topic = self.create_topic(title, keywords)

        elif result.action == ClassificationAction.RECALL:
            # Try to recall by topic_id or name
            topic = None
            if result.topic_id:
                topic = self.switch_topic(result.topic_id)
                if not topic:
                    topic = self.recall_topic_by_name(result.topic_id)

            if not topic:
                # Could not recall, treat as continue
                if self.current_topic_id and self.current_topic_id in self.topics:
                    topic = self.topics[self.current_topic_id]
                    topic.touch(tokens_estimate)
                else:
                    # No current topic, create new
                    topic = self.create_topic("Continued conversation", result.keywords or [])

        else:  # CONTINUE or MERGE
            if self.current_topic_id and self.current_topic_id in self.topics:
                topic = self.topics[self.current_topic_id]
                topic.touch(tokens_estimate)
                # Optionally merge keywords
                if result.keywords:
                    existing_keywords = set(topic.keywords)
                    for kw in result.keywords:
                        if kw not in existing_keywords:
                            topic.keywords.append(kw)
                    topic.keywords = topic.keywords[:10]  # Limit keywords
            else:
                # No current topic, create one
                title = result.new_title or "Conversation"
                topic = self.create_topic(title, result.keywords or extract_keywords_simple(message))

        self._save_topics()
        return topic, result

    def get_current_topic_info(self) -> Optional[dict]:
        """Get info about the current topic for display"""
        if not self.current_topic_id or self.current_topic_id not in self.topics:
            return None

        topic = self.topics[self.current_topic_id]
        return {
            "id": topic.id,
            "title": topic.title,
            "keywords": topic.keywords[:5],
            "message_count": topic.message_count,
            "status": topic.status.value,
            "active_topics": len(self.active_topic_ids),
            "total_topics": len(self.topics)
        }

    def clear_all_topics(self):
        """Clear all topics (for /new command)"""
        self.topics.clear()
        self.active_topic_ids.clear()
        self.current_topic_id = None
        self._save_topics()
        logger.info("Cleared all topics")
