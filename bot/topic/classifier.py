"""Topic classifier using 3-tier approach: heuristics -> Haiku -> full model"""

import logging
import re
from dataclasses import dataclass
from enum import Enum
from typing import Optional

logger = logging.getLogger(__name__)


class ClassificationAction(str, Enum):
    """Classification action types"""
    CONTINUE = "continue"  # Continue with current topic
    NEW = "new"  # Start a new topic
    RECALL = "recall"  # Recall an archived topic
    MERGE = "merge"  # Merge with existing topic


@dataclass
class ClassificationResult:
    """Result of topic classification"""
    action: ClassificationAction
    topic_id: Optional[str] = None  # Existing topic ID (for continue/recall)
    new_title: Optional[str] = None  # New topic title (for new action)
    keywords: list[str] = None  # Extracted keywords
    confidence: float = 1.0
    tier_used: int = 1  # Which tier made the decision (1=heuristic, 2=haiku, 3=full)

    def __post_init__(self):
        if self.keywords is None:
            self.keywords = []


# Signals that suggest a topic change
TOPIC_CHANGE_SIGNALS = [
    # Chinese
    "另外", "顺便", "换个话题", "说到", "对了", "还有", "btw", "by the way",
    "接下来", "下一个", "关于另一件事", "我想问", "还想问",
    # English
    "anyway", "moving on", "separately", "also", "different topic",
    "on another note", "switching gears", "quick question about"
]

# Signals that suggest continuing the same topic
CONTINUE_SIGNALS = [
    # Chinese
    "继续", "接着", "然后呢", "还有吗", "更多", "详细说说", "展开说说",
    "解释一下", "什么意思", "为什么", "怎么", "再说说", "帮我",
    # English
    "continue", "more", "elaborate", "explain", "why", "how", "what about",
    "tell me more", "go on", "and then"
]

# Short follow-up patterns (almost always same topic)
SHORT_FOLLOWUP_PATTERNS = [
    r"^好的?$", r"^ok$", r"^嗯$", r"^是的?$", r"^对$", r"^明白$",
    r"^收到$", r"^懂了$", r"^好吧$", r"^行$", r"^可以$",
    r"^yes$", r"^no$", r"^yeah$", r"^sure$", r"^got it$", r"^thanks?$",
    r"^谢谢$", r"^thx$", r"^ty$", r"^👍$", r"^[!?。？！]+$"
]


def quick_heuristic_check(
    message: str,
    current_topic_keywords: list[str] = None,
    current_topic_title: str = None
) -> Optional[ClassificationResult]:
    """
    Tier 1: Quick heuristic check (no API call).

    Returns ClassificationResult if confident, None if uncertain (needs Tier 2).
    """
    message_lower = message.lower().strip()

    # Rule 1: Very short messages are almost always same topic
    if len(message_lower) < 10:
        for pattern in SHORT_FOLLOWUP_PATTERNS:
            if re.match(pattern, message_lower, re.IGNORECASE):
                return ClassificationResult(
                    action=ClassificationAction.CONTINUE,
                    confidence=0.95,
                    tier_used=1
                )

    # Rule 2: Check for explicit topic change signals
    for signal in TOPIC_CHANGE_SIGNALS:
        if signal in message_lower:
            # Strong signal for new topic
            return ClassificationResult(
                action=ClassificationAction.NEW,
                confidence=0.85,
                tier_used=1
            )

    # Rule 3: Check for continuation signals
    for signal in CONTINUE_SIGNALS:
        if signal in message_lower:
            return ClassificationResult(
                action=ClassificationAction.CONTINUE,
                confidence=0.85,
                tier_used=1
            )

    # Rule 4: Keyword overlap with current topic (if available)
    if current_topic_keywords:
        keywords_lower = [k.lower() for k in current_topic_keywords]
        word_overlap = sum(1 for k in keywords_lower if k in message_lower)

        # Strong keyword overlap suggests same topic
        if word_overlap >= 2:
            return ClassificationResult(
                action=ClassificationAction.CONTINUE,
                confidence=0.80,
                tier_used=1
            )

    # Rule 5: Message directly references current topic title
    if current_topic_title and len(current_topic_title) > 5:
        # Check for partial title match
        title_words = current_topic_title.lower().split()
        title_match = sum(1 for w in title_words if w in message_lower and len(w) > 2)
        if title_match >= len(title_words) // 2:
            return ClassificationResult(
                action=ClassificationAction.CONTINUE,
                confidence=0.75,
                tier_used=1
            )

    # Uncertain - need Tier 2
    return None


async def classify_with_haiku(
    message: str,
    current_topic: Optional[dict],
    recent_topics: list[dict],
    archived_topics: list[dict],
    api_key: str,
    base_url: Optional[str] = None
) -> ClassificationResult:
    """
    Tier 2: Use Haiku for classification.

    Args:
        message: User message to classify
        current_topic: Current active topic info
        recent_topics: List of recent topic summaries
        archived_topics: List of archived topic titles
        api_key: Anthropic API key
        base_url: Optional API base URL

    Returns:
        ClassificationResult
    """
    import anthropic
    import json

    # Build context for Haiku
    context_parts = []

    if current_topic:
        context_parts.append(f"Current topic: {current_topic.get('title', 'Unknown')}")
        if current_topic.get('keywords'):
            context_parts.append(f"Keywords: {', '.join(current_topic['keywords'][:5])}")

    if recent_topics:
        recent_str = ", ".join(t.get('title', 'Unknown') for t in recent_topics[:3])
        context_parts.append(f"Recent topics: {recent_str}")

    if archived_topics:
        archived_str = ", ".join(t.get('title', 'Unknown') for t in archived_topics[:5])
        context_parts.append(f"Archived topics: {archived_str}")

    context = "\n".join(context_parts) if context_parts else "No previous topics"

    prompt = f"""Analyze this user message and determine if it continues the current topic or starts a new one.

Context:
{context}

User message: {message}

Respond with ONLY a JSON object (no markdown):
{{
    "action": "continue" or "new" or "recall",
    "topic_id": null or "existing topic name if recalling",
    "new_title": null or "short title if new topic (max 10 words)",
    "keywords": ["keyword1", "keyword2", "keyword3"],
    "confidence": 0.0 to 1.0
}}

Rules:
- "continue": Message is about the current topic or a follow-up
- "new": Message starts a completely new topic
- "recall": Message references an archived topic (set topic_id to the topic name)
- Extract 3-5 keywords from the message regardless of action"""

    try:
        client_args = {"api_key": api_key}
        if base_url:
            client_args["base_url"] = base_url

        client = anthropic.Anthropic(**client_args)

        response = client.messages.create(
            model="claude-3-5-haiku-20241022",
            max_tokens=200,
            messages=[{"role": "user", "content": prompt}]
        )

        result_text = response.content[0].text.strip()

        # Parse JSON response
        # Handle potential markdown code blocks
        if result_text.startswith("```"):
            result_text = result_text.split("```")[1]
            if result_text.startswith("json"):
                result_text = result_text[4:]
            result_text = result_text.strip()

        data = json.loads(result_text)

        action_str = data.get("action", "continue")
        action = ClassificationAction(action_str) if action_str in ClassificationAction.__members__.values() else ClassificationAction.CONTINUE

        return ClassificationResult(
            action=action,
            topic_id=data.get("topic_id"),
            new_title=data.get("new_title"),
            keywords=data.get("keywords", []),
            confidence=float(data.get("confidence", 0.8)),
            tier_used=2
        )

    except Exception as e:
        logger.error(f"Haiku classification failed: {e}")
        # Fallback to continue (safer default)
        return ClassificationResult(
            action=ClassificationAction.CONTINUE,
            confidence=0.5,
            tier_used=2
        )


def extract_keywords_simple(message: str, count: int = 5) -> list[str]:
    """
    Extract keywords from message using simple heuristics.
    Used when Haiku is not available.
    """
    import re

    # Remove common stop words and punctuation
    stop_words = {
        'the', 'a', 'an', 'is', 'are', 'was', 'were', 'be', 'been', 'being',
        'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would', 'could',
        'should', 'may', 'might', 'must', 'can', 'and', 'or', 'but', 'in',
        'on', 'at', 'to', 'for', 'of', 'with', 'by', 'from', 'this', 'that',
        'it', 'its', 'i', 'you', 'he', 'she', 'we', 'they', 'my', 'your',
        'what', 'which', 'who', 'when', 'where', 'why', 'how', 'me', 'him',
        'her', 'us', 'them', 'if', 'then', 'so', 'as', 'just', 'about',
        # Chinese stop words
        '的', '是', '在', '了', '有', '和', '我', '你', '他', '她', '它',
        '这', '那', '都', '也', '就', '要', '会', '能', '可以', '不', '吗',
        '呢', '啊', '吧', '么', '一个', '什么', '怎么', '为什么', '如何'
    }

    # Tokenize (simple approach)
    words = re.findall(r'[\w\u4e00-\u9fff]+', message.lower())

    # Filter and score
    keywords = []
    for word in words:
        if word not in stop_words and len(word) > 1:
            # Prefer longer words and words with numbers (like stock symbols)
            score = len(word) + (2 if any(c.isdigit() for c in word) else 0)
            keywords.append((word, score))

    # Sort by score and take top N
    keywords.sort(key=lambda x: x[1], reverse=True)
    return [w for w, _ in keywords[:count]]


class TopicClassifier:
    """
    Topic classifier with 3-tier approach.
    """

    def __init__(self, api_key: str, base_url: Optional[str] = None):
        self.api_key = api_key
        self.base_url = base_url

    async def classify(
        self,
        message: str,
        current_topic: Optional[dict] = None,
        recent_topics: list[dict] = None,
        archived_topics: list[dict] = None
    ) -> ClassificationResult:
        """
        Classify a message using the 3-tier approach.

        Args:
            message: User message
            current_topic: Current topic info (title, keywords)
            recent_topics: Recent topic summaries
            archived_topics: Archived topic titles

        Returns:
            ClassificationResult
        """
        recent_topics = recent_topics or []
        archived_topics = archived_topics or []

        # Tier 1: Heuristics (free)
        heuristic_result = quick_heuristic_check(
            message,
            current_topic.get('keywords', []) if current_topic else [],
            current_topic.get('title') if current_topic else None
        )

        if heuristic_result:
            # Add keywords if action is NEW
            if heuristic_result.action == ClassificationAction.NEW:
                heuristic_result.keywords = extract_keywords_simple(message)
            return heuristic_result

        # Tier 2: Haiku ($0.0003)
        if self.api_key:
            haiku_result = await classify_with_haiku(
                message,
                current_topic,
                recent_topics,
                archived_topics,
                self.api_key,
                self.base_url
            )

            # Tier 3: If Haiku is uncertain (confidence < 0.6), could use full model
            # For now, we just accept Haiku's result
            if haiku_result.confidence < 0.6:
                logger.warning(f"Low confidence classification: {haiku_result.confidence}")

            return haiku_result

        # Fallback: No API key, use heuristics default
        return ClassificationResult(
            action=ClassificationAction.CONTINUE,
            keywords=extract_keywords_simple(message),
            confidence=0.5,
            tier_used=1
        )
