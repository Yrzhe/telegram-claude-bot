"""Memory manager - handles memory CRUD and analysis"""

import json
import logging
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

from .models import (
    Memory, MemoryStore, MemoryVisibility, MemoryCategory,
    UserMemoryPreferences, DEFAULT_VISIBILITY
)

logger = logging.getLogger(__name__)


class MemoryManager:
    """Manages user memories with visibility, deduplication, and preference learning"""

    def __init__(self, user_data_dir: Path):
        """
        Initialize memory manager for a user

        Args:
            user_data_dir: Path to user's data directory (e.g., /app/users/{user_id})
        """
        self.user_data_dir = Path(user_data_dir)
        self.memories_file = self.user_data_dir / "data" / "memories.json"
        self._store: Optional[MemoryStore] = None

    def _ensure_loaded(self) -> MemoryStore:
        """Ensure memory store is loaded"""
        if self._store is None:
            self._store = self._load_store()
        return self._store

    def _load_store(self) -> MemoryStore:
        """Load memory store from file"""
        if self.memories_file.exists():
            try:
                data = json.loads(self.memories_file.read_text(encoding='utf-8'))
                # Handle legacy format (just memories array)
                if "memories" in data and isinstance(data["memories"], list):
                    # Check if it's new format or legacy
                    if "preferences" not in data:
                        # Legacy format - convert
                        return self._migrate_legacy_format(data)
                    return MemoryStore.from_dict(data)
            except Exception as e:
                logger.error(f"Failed to load memories: {e}")
        return MemoryStore()

    def _migrate_legacy_format(self, data: dict) -> MemoryStore:
        """Migrate from legacy format to new format"""
        memories = []
        for m in data.get("memories", []):
            # Add new fields with defaults
            memory = Memory(
                id=m.get("id", self._generate_id()),
                content=m.get("content", ""),
                category=m.get("category", "context"),
                visibility=m.get("visibility", DEFAULT_VISIBILITY.get(
                    m.get("category", "context"),
                    MemoryVisibility.PRIVATE
                ).value),
                source_type=m.get("source_type", "explicit"),
                confidence=m.get("confidence", 1.0),
                user_confirmed=m.get("user_confirmed", True),  # Existing memories are trusted
                supersedes=m.get("supersedes"),
                superseded_by=m.get("superseded_by"),
                tags=m.get("tags", []),
                created_at=m.get("created_at", ""),
                valid_from=m.get("valid_from", ""),
                valid_until=m.get("valid_until"),
                related_to=m.get("related_to", []),
            )
            memories.append(memory)

        store = MemoryStore(
            memories=memories,
            preferences=UserMemoryPreferences(),
            total_memories_created=len(memories),
        )

        # Save migrated format
        self._save_store(store)
        logger.info(f"Migrated {len(memories)} memories to new format")
        return store

    def _save_store(self, store: Optional[MemoryStore] = None) -> bool:
        """Save memory store to file"""
        if store is None:
            store = self._store
        if store is None:
            return False

        try:
            store.last_updated = datetime.now().isoformat()
            self.memories_file.parent.mkdir(parents=True, exist_ok=True)
            self.memories_file.write_text(
                json.dumps(store.to_dict(), ensure_ascii=False, indent=2),
                encoding='utf-8'
            )
            return True
        except Exception as e:
            logger.error(f"Failed to save memories: {e}")
            return False

    def _generate_id(self) -> str:
        """Generate a unique memory ID"""
        now = datetime.now()
        return f"mem_{now.strftime('%Y%m%d')}_{uuid.uuid4().hex[:6]}"

    # ==================== Core Operations ====================

    def save_memory(
        self,
        content: str,
        category: str,
        source_type: str = "inferred",
        confidence: float = 0.8,
        tags: list[str] = None,
        valid_from: str = None,
        related_to: list[str] = None,
        visibility: str = None,
    ) -> tuple[Memory, str]:
        """
        Save a new memory

        Args:
            content: The memory content
            category: Memory category
            source_type: "explicit" or "inferred"
            confidence: Confidence level (0.0 to 1.0)
            tags: Keywords for searching
            valid_from: When this became true (YYYY-MM-DD)
            related_to: Related memory IDs
            visibility: Override visibility (public/private)

        Returns:
            Tuple of (Memory object, formatted notification message)
        """
        store = self._ensure_loaded()

        # Check for duplicates
        for existing in store.memories:
            if existing.content.lower() == content.lower() and existing.is_active():
                return existing, ""  # Already exists, no notification

        # Determine visibility
        if visibility is None:
            visibility = store.preferences.get_visibility_for_category(category)

        # Create memory
        memory = Memory(
            id=self._generate_id(),
            content=content,
            category=category,
            visibility=visibility,
            source_type=source_type,
            confidence=confidence,
            user_confirmed=False,
            tags=tags or [],
            valid_from=valid_from or datetime.now().strftime("%Y-%m-%d"),
            related_to=related_to or [],
        )

        # Insert at beginning (newest first)
        store.memories.insert(0, memory)
        store.total_memories_created += 1
        self._save_store()

        # Format notification
        notification = self._format_memory_notification(memory)

        logger.info(f"Saved memory {memory.id}: {content[:50]}...")
        return memory, notification

    def save_memory_with_supersede(
        self,
        content: str,
        category: str,
        supersedes_id: str,
        source_type: str = "inferred",
        confidence: float = 0.8,
        tags: list[str] = None,
        visibility: str = None,
    ) -> tuple[Memory, str]:
        """
        Save a new memory that supersedes an old one

        Args:
            content: The new memory content
            category: Memory category
            supersedes_id: ID of the memory being superseded
            source_type: "explicit" or "inferred"
            confidence: Confidence level
            tags: Keywords
            visibility: Override visibility

        Returns:
            Tuple of (new Memory, notification message)
        """
        store = self._ensure_loaded()

        # Find and update the old memory
        old_memory = None
        for m in store.memories:
            if m.id == supersedes_id:
                old_memory = m
                break

        if old_memory is None:
            # Old memory not found, just save as new
            return self.save_memory(
                content=content,
                category=category,
                source_type=source_type,
                confidence=confidence,
                tags=tags,
                visibility=visibility,
            )

        # Determine visibility (inherit from old if not specified)
        if visibility is None:
            visibility = old_memory.visibility

        # Create new memory
        new_memory = Memory(
            id=self._generate_id(),
            content=content,
            category=category,
            visibility=visibility,
            source_type=source_type,
            confidence=confidence,
            user_confirmed=False,
            supersedes=supersedes_id,
            tags=tags or old_memory.tags,
            valid_from=datetime.now().strftime("%Y-%m-%d"),
            related_to=old_memory.related_to.copy() if old_memory.related_to else [],
        )

        # Mark old memory as superseded
        old_memory.superseded_by = new_memory.id
        old_memory.valid_until = datetime.now().strftime("%Y-%m-%d")

        # Insert new memory
        store.memories.insert(0, new_memory)
        store.total_memories_created += 1
        self._save_store()

        # Format notification with update indication
        notification = self._format_memory_update_notification(new_memory, old_memory)

        logger.info(f"Memory {supersedes_id} superseded by {new_memory.id}")
        return new_memory, notification

    def update_memory(
        self,
        memory_id: str,
        content: str = None,
        visibility: str = None,
        user_confirmed: bool = None,
        tags: list[str] = None,
    ) -> tuple[bool, str]:
        """
        Update an existing memory

        Returns:
            Tuple of (success, message)
        """
        store = self._ensure_loaded()

        for memory in store.memories:
            if memory.id == memory_id:
                if content is not None:
                    memory.content = content
                if visibility is not None:
                    memory.visibility = visibility
                    # Learn from user correction
                    self._learn_visibility_preference(memory.category, visibility)
                if user_confirmed is not None:
                    memory.user_confirmed = user_confirmed
                if tags is not None:
                    memory.tags = tags

                store.total_user_corrections += 1
                self._save_store()
                return True, f"Memory {memory_id} updated"

        return False, f"Memory {memory_id} not found"

    def delete_memory(self, memory_id: str) -> tuple[bool, str]:
        """Delete a memory by ID"""
        store = self._ensure_loaded()

        for i, memory in enumerate(store.memories):
            if memory.id == memory_id:
                deleted = store.memories.pop(i)
                store.total_memories_deleted += 1
                self._save_store()
                return True, f"Deleted: {deleted.content[:50]}..."

        return False, f"Memory {memory_id} not found"

    def search_memories(
        self,
        query: str = None,
        category: str = None,
        visibility: str = None,
        active_only: bool = True,
        limit: int = 10,
    ) -> list[Memory]:
        """
        Search memories

        Args:
            query: Keyword to search in content and tags
            category: Filter by category
            visibility: Filter by visibility (public/private)
            active_only: Only return non-superseded memories
            limit: Max results

        Returns:
            List of matching memories
        """
        store = self._ensure_loaded()
        results = []

        for memory in store.memories:
            # Filter by active status
            if active_only and not memory.is_active():
                continue

            # Filter by category
            if category and memory.category != category:
                continue

            # Filter by visibility
            if visibility and memory.visibility != visibility:
                continue

            # Filter by query
            if query:
                query_lower = query.lower()
                if query_lower not in memory.content.lower():
                    if not any(query_lower in tag.lower() for tag in memory.tags):
                        continue

            results.append(memory)

            if len(results) >= limit:
                break

        return results

    def get_category_timeline(self, category: str) -> list[Memory]:
        """Get all memories in a category as a timeline (oldest first)"""
        store = self._ensure_loaded()
        memories = [m for m in store.memories if m.category == category]
        # Sort by valid_from (oldest first for timeline)
        memories.sort(key=lambda m: m.valid_from)
        return memories

    def get_public_memories(self) -> list[Memory]:
        """Get all public memories (for group context)"""
        return self.search_memories(visibility=MemoryVisibility.PUBLIC.value, limit=100)

    # ==================== Preference Learning ====================

    def _learn_visibility_preference(self, category: str, visibility: str):
        """Learn from user's visibility correction"""
        store = self._ensure_loaded()
        store.preferences.visibility_overrides[category] = visibility
        logger.info(f"Learned visibility preference: {category} -> {visibility}")

    def set_category_visibility(self, category: str, visibility: str) -> bool:
        """Explicitly set visibility for a category"""
        if visibility not in [MemoryVisibility.PUBLIC.value, MemoryVisibility.PRIVATE.value]:
            return False
        store = self._ensure_loaded()
        store.preferences.visibility_overrides[category] = visibility
        self._save_store()
        return True

    def get_preferences(self) -> UserMemoryPreferences:
        """Get user's memory preferences"""
        store = self._ensure_loaded()
        return store.preferences

    # ==================== Notification Formatting ====================

    def _format_memory_notification(self, memory: Memory) -> str:
        """Format a memory notification for Telegram (expandable blockquote)"""
        visibility_emoji = "🌐" if memory.visibility == MemoryVisibility.PUBLIC.value else "🔒"
        visibility_text = "公开" if memory.visibility == MemoryVisibility.PUBLIC.value else "私密"

        # Category display names
        category_names = {
            "personal": "个人",
            "family": "家庭",
            "career": "职业",
            "education": "教育",
            "interests": "兴趣",
            "preferences": "偏好",
            "goals": "目标",
            "finance": "财务",
            "health": "健康",
            "schedule": "日程",
            "context": "背景",
            "relationships": "关系",
            "emotions": "情绪",
        }
        category_display = category_names.get(memory.category, memory.category)

        # Use expandable blockquote
        notification = f"""<blockquote expandable>
📝 记住了：「{memory.content}」
📂 {category_display} | {visibility_emoji} {visibility_text}
回复可修改~
</blockquote>"""

        return notification

    def _format_memory_update_notification(self, new_memory: Memory, old_memory: Memory) -> str:
        """Format a memory update notification"""
        visibility_emoji = "🌐" if new_memory.visibility == MemoryVisibility.PUBLIC.value else "🔒"
        visibility_text = "公开" if new_memory.visibility == MemoryVisibility.PUBLIC.value else "私密"

        category_names = {
            "personal": "个人",
            "family": "家庭",
            "career": "职业",
            "education": "教育",
            "interests": "兴趣",
            "preferences": "偏好",
            "goals": "目标",
            "finance": "财务",
            "health": "健康",
            "schedule": "日程",
            "context": "背景",
            "relationships": "关系",
            "emotions": "情绪",
        }
        category_display = category_names.get(new_memory.category, new_memory.category)

        notification = f"""<blockquote expandable>
📝 更新了：「{new_memory.content}」
📂 {category_display} | {visibility_emoji} {visibility_text}
🔄 替代：「{old_memory.content[:30]}...」
回复可修改~
</blockquote>"""

        return notification

    def format_memories_summary(self, memories: list[Memory]) -> str:
        """Format multiple memories for batch notification"""
        if not memories:
            return ""

        lines = ["<blockquote expandable>", f"📝 本次对话记住了 {len(memories)} 条信息："]
        for m in memories[:5]:  # Show max 5
            visibility_emoji = "🌐" if m.visibility == MemoryVisibility.PUBLIC.value else "🔒"
            lines.append(f"• {m.content[:40]}... {visibility_emoji}")

        if len(memories) > 5:
            lines.append(f"... 还有 {len(memories) - 5} 条")

        lines.append("回复可查看或修改~")
        lines.append("</blockquote>")

        return "\n".join(lines)

    # ==================== Stats ====================

    def get_stats(self) -> dict:
        """Get memory statistics"""
        store = self._ensure_loaded()

        # Count by category
        by_category = {}
        by_visibility = {"public": 0, "private": 0}
        active_count = 0

        for m in store.memories:
            by_category[m.category] = by_category.get(m.category, 0) + 1
            by_visibility[m.visibility] = by_visibility.get(m.visibility, 0) + 1
            if m.is_active():
                active_count += 1

        return {
            "total": len(store.memories),
            "active": active_count,
            "by_category": by_category,
            "by_visibility": by_visibility,
            "total_created": store.total_memories_created,
            "total_deleted": store.total_memories_deleted,
            "total_corrections": store.total_user_corrections,
        }
