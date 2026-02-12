"""Session 管理器 - 管理用户的 Agent 会话"""

import json
import logging
import time
from pathlib import Path
from dataclasses import dataclass, asdict
from typing import Dict, Optional

logger = logging.getLogger(__name__)


@dataclass
class SessionInfo:
    """会话信息"""
    session_id: str
    user_id: int
    created_at: float
    last_active_at: float
    message_count: int = 0
    # Usage statistics
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_cost_usd: float = 0.0
    total_turns: int = 0
    # Context compaction
    compact_count: int = 0  # Number of times this session has been compacted
    # Topic tracking
    current_topic_id: Optional[str] = None  # Current topic ID from TopicManager

    def is_expired(self, timeout_seconds: int = 3600) -> bool:
        """检查会话是否过期（默认1小时，0表示永不过期）"""
        if timeout_seconds <= 0:
            return False  # 永不过期
        return time.time() - self.last_active_at > timeout_seconds

    def touch(self):
        """更新最后活跃时间"""
        self.last_active_at = time.time()
        self.message_count += 1


class SessionManager:
    """管理用户的 Agent 会话"""

    def __init__(
        self,
        sessions_file: str | Path,
        session_timeout: int = 3600  # 1小时
    ):
        """
        初始化 Session 管理器

        Args:
            sessions_file: 会话数据存储文件路径
            session_timeout: 会话超时时间（秒）
        """
        self.sessions_file = Path(sessions_file)
        self.session_timeout = session_timeout
        self._sessions: Dict[int, SessionInfo] = {}
        self._load_sessions()

    def _load_sessions(self):
        """从文件加载会话数据"""
        if self.sessions_file.exists():
            try:
                data = json.loads(self.sessions_file.read_text(encoding='utf-8'))
                for user_id_str, session_data in data.items():
                    user_id = int(user_id_str)
                    self._sessions[user_id] = SessionInfo(
                        session_id=session_data['session_id'],
                        user_id=user_id,
                        created_at=session_data['created_at'],
                        last_active_at=session_data['last_active_at'],
                        message_count=session_data.get('message_count', 0),
                        total_input_tokens=session_data.get('total_input_tokens', 0),
                        total_output_tokens=session_data.get('total_output_tokens', 0),
                        total_cost_usd=session_data.get('total_cost_usd', 0.0),
                        total_turns=session_data.get('total_turns', 0),
                        compact_count=session_data.get('compact_count', 0),
                        current_topic_id=session_data.get('current_topic_id')
                    )
                logger.info(f"加载了 {len(self._sessions)} 个会话")
            except Exception as e:
                logger.error(f"加载会话数据失败: {e}")

    def _save_sessions(self):
        """保存会话数据到文件"""
        try:
            self.sessions_file.parent.mkdir(parents=True, exist_ok=True)
            data = {
                str(user_id): asdict(session)
                for user_id, session in self._sessions.items()
            }
            self.sessions_file.write_text(
                json.dumps(data, indent=2),
                encoding='utf-8'
            )
        except Exception as e:
            logger.error(f"保存会话数据失败: {e}")

    def get_session(self, user_id: int) -> Optional[SessionInfo]:
        """
        获取用户的会话（如果存在且未过期）

        Args:
            user_id: 用户 ID

        Returns:
            会话信息，如果不存在或已过期则返回 None
        """
        session = self._sessions.get(user_id)

        if session is None:
            return None

        # 检查是否过期
        if session.is_expired(self.session_timeout):
            logger.info(f"用户 {user_id} 的会话已过期，清除")
            self.clear_session(user_id)
            return None

        return session

    def pop_expired_session_id(self, user_id: int) -> Optional[str]:
        """If user has an expired session, return its session_id and clear it.
        Returns None if no session or session is still valid."""
        session = self._sessions.get(user_id)
        if session is None:
            return None
        if session.is_expired(self.session_timeout):
            expired_id = session.session_id
            self.clear_session(user_id)
            return expired_id if expired_id else None
        return None

    def get_session_id(self, user_id: int) -> Optional[str]:
        """获取用户的会话 ID（用于 resume）"""
        session = self.get_session(user_id)
        return session.session_id if session else None

    def create_session(self, user_id: int, session_id: str) -> SessionInfo:
        """
        创建新会话

        Args:
            user_id: 用户 ID
            session_id: 会话 ID（从 Agent 返回）

        Returns:
            新创建的会话信息
        """
        now = time.time()
        session = SessionInfo(
            session_id=session_id,
            user_id=user_id,
            created_at=now,
            last_active_at=now,
            message_count=1
        )
        self._sessions[user_id] = session
        self._save_sessions()
        logger.info(f"为用户 {user_id} 创建新会话: {session_id}")
        return session

    def update_session(
        self,
        user_id: int,
        session_id: str | None = None,
        usage: dict | None = None,
        topic_id: str | None = None
    ):
        """
        更新会话（更新活跃时间和消息计数）

        Args:
            user_id: 用户 ID
            session_id: 新的会话 ID（如果需要更新）
            usage: 使用统计信息 {input_tokens, output_tokens, cost_usd, turns}
            topic_id: 当前话题 ID
        """
        session = self._sessions.get(user_id)
        if session:
            session.touch()
            if session_id:
                session.session_id = session_id
            if topic_id:
                session.current_topic_id = topic_id
            # Update usage statistics
            if usage:
                session.total_input_tokens += usage.get('input_tokens', 0)
                session.total_output_tokens += usage.get('output_tokens', 0)
                session.total_cost_usd += usage.get('cost_usd', 0.0)
                session.total_turns += usage.get('turns', 0)
            self._save_sessions()

    def get_current_topic_id(self, user_id: int) -> Optional[str]:
        """获取用户当前的话题 ID"""
        session = self.get_session(user_id)
        return session.current_topic_id if session else None

    def set_current_topic_id(self, user_id: int, topic_id: str | None):
        """设置用户当前的话题 ID"""
        session = self._sessions.get(user_id)
        if session:
            session.current_topic_id = topic_id
            self._save_sessions()

    def clear_session(self, user_id: int) -> bool:
        """
        清除用户的会话

        Args:
            user_id: 用户 ID

        Returns:
            是否成功清除
        """
        if user_id in self._sessions:
            del self._sessions[user_id]
            self._save_sessions()
            logger.info(f"清除用户 {user_id} 的会话")
            return True
        return False

    def get_session_info(self, user_id: int) -> Optional[dict]:
        """获取会话的详细信息（用于显示给用户）"""
        session = self.get_session(user_id)
        if not session:
            return None

        elapsed = time.time() - session.last_active_at

        # Handle no-timeout mode
        if self.session_timeout <= 0:
            remaining = -1  # -1 means no expiry
            remaining_minutes = -1
        else:
            remaining = max(0, self.session_timeout - elapsed)
            remaining_minutes = int(remaining / 60)

        return {
            "session_id": session.session_id[:8] + "...",  # 只显示前8位
            "created_at": session.created_at,
            "last_active_at": session.last_active_at,
            "message_count": session.message_count,
            "elapsed_seconds": int(elapsed),
            "remaining_seconds": int(remaining),
            "remaining_minutes": remaining_minutes,
            "no_expiry": self.session_timeout <= 0,
            # Usage statistics
            "total_input_tokens": session.total_input_tokens,
            "total_output_tokens": session.total_output_tokens,
            "total_tokens": session.total_input_tokens + session.total_output_tokens,
            "total_cost_usd": session.total_cost_usd,
            "total_turns": session.total_turns,
            "compact_count": session.compact_count,
            # Topic tracking
            "current_topic_id": session.current_topic_id
        }

    def cleanup_expired_sessions(self):
        """清理所有过期的会话"""
        expired_users = [
            user_id for user_id, session in self._sessions.items()
            if session.is_expired(self.session_timeout)
        ]
        for user_id in expired_users:
            self.clear_session(user_id)

        if expired_users:
            logger.info(f"清理了 {len(expired_users)} 个过期会话")

    def get_all_sessions_info(self) -> list[dict]:
        """获取所有会话信息（管理员用）"""
        self.cleanup_expired_sessions()
        return [
            {
                "user_id": session.user_id,
                "session_id": session.session_id[:8] + "...",
                "message_count": session.message_count,
                "last_active": int(time.time() - session.last_active_at)
            }
            for session in self._sessions.values()
        ]

    def compact_session(self, user_id: int) -> Optional[dict]:
        """
        压缩会话上下文（清除 session_id 但保留统计信息）

        Args:
            user_id: 用户 ID

        Returns:
            压缩前的会话信息，如果没有会话则返回 None
        """
        session = self._sessions.get(user_id)
        if not session:
            return None

        # 保存当前统计信息
        old_info = {
            "session_id": session.session_id,
            "message_count": session.message_count,
            "total_input_tokens": session.total_input_tokens,
            "total_output_tokens": session.total_output_tokens,
            "total_cost_usd": session.total_cost_usd,
            "total_turns": session.total_turns,
            "compact_count": session.compact_count
        }

        # 清除会话 ID 但保留统计信息
        # 新会话会继承统计
        session.session_id = ""
        session.compact_count += 1
        session.last_active_at = time.time()
        self._save_sessions()

        logger.info(f"用户 {user_id} 会话已压缩 (第 {session.compact_count} 次)")
        return old_info

    def end_session(self, user_id: int) -> bool:
        """
        结束会话（清除 session_id，保留用户记录）

        与 clear_session 不同，这只是清除 session_id 以便下次创建新会话
        """
        session = self._sessions.get(user_id)
        if session:
            session.session_id = ""
            self._save_sessions()
            logger.info(f"用户 {user_id} 会话已结束")
            return True
        return False

    def needs_compaction(self, user_id: int, threshold_tokens: int = 150000) -> bool:
        """
        检查会话是否需要压缩

        Args:
            user_id: 用户 ID
            threshold_tokens: Token 阈值（默认 150K，约为 Claude 上下文的 75%）

        Returns:
            是否需要压缩
        """
        session = self._sessions.get(user_id)
        if not session:
            return False

        total_tokens = session.total_input_tokens + session.total_output_tokens
        return total_tokens >= threshold_tokens
