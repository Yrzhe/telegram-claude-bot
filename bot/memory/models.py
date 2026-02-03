"""Memory data models"""

from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
from typing import Optional


class MemoryVisibility(str, Enum):
    """Memory visibility levels"""
    PUBLIC = "public"    # Can be used in group context
    PRIVATE = "private"  # Only for private conversations


class MemoryCategory(str, Enum):
    """Memory categories"""
    PERSONAL = "personal"      # Name, age, birthday, location
    FAMILY = "family"          # Relationships, family members
    CAREER = "career"          # Job, company, work history
    EDUCATION = "education"    # School, degrees, certifications
    INTERESTS = "interests"    # Hobbies, topics of interest
    PREFERENCES = "preferences"  # Communication style, format preferences
    GOALS = "goals"            # Projects, objectives, aspirations
    FINANCE = "finance"        # Investment interests, financial goals
    HEALTH = "health"          # Health conditions, fitness goals
    SCHEDULE = "schedule"      # Regular routines, availability
    CONTEXT = "context"        # Background info, ongoing situations
    RELATIONSHIPS = "relationships"  # Friends, colleagues, social connections
    EMOTIONS = "emotions"      # Emotional patterns, what affects mood


# Default visibility rules for each category
DEFAULT_VISIBILITY: dict[str, MemoryVisibility] = {
    MemoryCategory.CAREER.value: MemoryVisibility.PUBLIC,
    MemoryCategory.INTERESTS.value: MemoryVisibility.PUBLIC,
    MemoryCategory.GOALS.value: MemoryVisibility.PUBLIC,
    MemoryCategory.EDUCATION.value: MemoryVisibility.PUBLIC,
    MemoryCategory.PREFERENCES.value: MemoryVisibility.PRIVATE,
    MemoryCategory.PERSONAL.value: MemoryVisibility.PRIVATE,
    MemoryCategory.FAMILY.value: MemoryVisibility.PRIVATE,
    MemoryCategory.RELATIONSHIPS.value: MemoryVisibility.PRIVATE,
    MemoryCategory.EMOTIONS.value: MemoryVisibility.PRIVATE,
    MemoryCategory.HEALTH.value: MemoryVisibility.PRIVATE,
    MemoryCategory.FINANCE.value: MemoryVisibility.PRIVATE,
    MemoryCategory.SCHEDULE.value: MemoryVisibility.PRIVATE,
    MemoryCategory.CONTEXT.value: MemoryVisibility.PRIVATE,
}


@dataclass
class Memory:
    """A single memory about the user"""
    id: str
    content: str
    category: str
    visibility: str = MemoryVisibility.PRIVATE.value
    source_type: str = "inferred"  # explicit or inferred
    confidence: float = 1.0  # 0.0 to 1.0, how confident AI is about this
    user_confirmed: bool = False  # User has confirmed this is correct
    supersedes: Optional[str] = None  # ID of memory this replaces
    superseded_by: Optional[str] = None  # ID of memory that replaced this
    tags: list[str] = field(default_factory=list)
    created_at: str = ""
    valid_from: str = ""
    valid_until: Optional[str] = None
    related_to: list[str] = field(default_factory=list)

    def __post_init__(self):
        if not self.created_at:
            self.created_at = datetime.now().isoformat()
        if not self.valid_from:
            self.valid_from = datetime.now().strftime("%Y-%m-%d")

    def is_active(self) -> bool:
        """Check if this memory is still active (not superseded)"""
        return self.superseded_by is None

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization"""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "Memory":
        """Create from dictionary"""
        return cls(**data)


@dataclass
class UserMemoryPreferences:
    """User's preferences for memory management"""
    # Override default visibility for specific categories
    visibility_overrides: dict[str, str] = field(default_factory=dict)

    # Learned rules from user corrections
    # Format: [{"pattern": "xxx", "category": "yyy", "visibility": "zzz"}]
    learned_rules: list[dict] = field(default_factory=list)

    # Categories user doesn't want to be tracked
    disabled_categories: list[str] = field(default_factory=list)

    def get_visibility_for_category(self, category: str) -> str:
        """Get the visibility setting for a category"""
        # Check user override first
        if category in self.visibility_overrides:
            return self.visibility_overrides[category]
        # Fall back to default
        return DEFAULT_VISIBILITY.get(category, MemoryVisibility.PRIVATE).value

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "UserMemoryPreferences":
        return cls(**data)


@dataclass
class MemoryStore:
    """Complete memory store for a user"""
    memories: list[Memory] = field(default_factory=list)
    preferences: UserMemoryPreferences = field(default_factory=UserMemoryPreferences)
    last_updated: str = ""

    # Statistics
    total_memories_created: int = 0
    total_memories_deleted: int = 0
    total_user_corrections: int = 0

    def __post_init__(self):
        if not self.last_updated:
            self.last_updated = datetime.now().isoformat()

    def to_dict(self) -> dict:
        return {
            "memories": [m.to_dict() for m in self.memories],
            "preferences": self.preferences.to_dict(),
            "last_updated": self.last_updated,
            "total_memories_created": self.total_memories_created,
            "total_memories_deleted": self.total_memories_deleted,
            "total_user_corrections": self.total_user_corrections,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "MemoryStore":
        memories = [Memory.from_dict(m) for m in data.get("memories", [])]
        prefs_data = data.get("preferences", {})
        preferences = UserMemoryPreferences.from_dict(prefs_data) if prefs_data else UserMemoryPreferences()
        return cls(
            memories=memories,
            preferences=preferences,
            last_updated=data.get("last_updated", ""),
            total_memories_created=data.get("total_memories_created", len(memories)),
            total_memories_deleted=data.get("total_memories_deleted", 0),
            total_user_corrections=data.get("total_user_corrections", 0),
        )
