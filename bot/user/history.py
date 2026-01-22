"""对话历史记录管理器"""

import json
import logging
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Any
from dataclasses import dataclass, asdict

logger = logging.getLogger(__name__)


@dataclass
class ChatRecord:
    """单条对话记录"""
    timestamp: float  # Unix 时间戳
    user_message: str  # 用户消息
    agent_response: Optional[str]  # Agent 回复
    session_id: Optional[str]  # 会话 ID
    is_error: bool = False  # 是否出错
    cost_usd: float = 0.0  # 花费（美元）

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> 'ChatRecord':
        return cls(
            timestamp=data.get('timestamp', 0),
            user_message=data.get('user_message', ''),
            agent_response=data.get('agent_response'),
            session_id=data.get('session_id'),
            is_error=data.get('is_error', False),
            cost_usd=data.get('cost_usd', 0.0)
        )


class HistoryManager:
    """对话历史管理器"""

    def __init__(self, base_path: str | Path):
        """
        初始化历史管理器

        Args:
            base_path: 用户数据根目录
        """
        self.base_path = Path(base_path)
        self.history_dir = self.base_path / "history"
        self.history_dir.mkdir(parents=True, exist_ok=True)

    def _get_user_history_file(self, user_id: int) -> Path:
        """获取用户历史文件路径"""
        return self.history_dir / f"{user_id}.json"

    def _load_user_history(self, user_id: int) -> List[Dict]:
        """加载用户历史记录"""
        history_file = self._get_user_history_file(user_id)
        if not history_file.exists():
            return []
        try:
            data = json.loads(history_file.read_text(encoding='utf-8'))
            return data.get('records', [])
        except Exception as e:
            logger.error(f"加载用户 {user_id} 历史记录失败: {e}")
            return []

    def _save_user_history(self, user_id: int, records: List[Dict]) -> bool:
        """保存用户历史记录"""
        try:
            history_file = self._get_user_history_file(user_id)
            data = {'records': records, 'updated_at': datetime.now().isoformat()}
            history_file.write_text(
                json.dumps(data, ensure_ascii=False, indent=2),
                encoding='utf-8'
            )
            return True
        except Exception as e:
            logger.error(f"保存用户 {user_id} 历史记录失败: {e}")
            return False

    def add_record(
        self,
        user_id: int,
        user_message: str,
        agent_response: Optional[str] = None,
        session_id: Optional[str] = None,
        is_error: bool = False,
        cost_usd: float = 0.0
    ) -> bool:
        """
        添加对话记录

        Args:
            user_id: 用户 ID
            user_message: 用户消息
            agent_response: Agent 回复
            session_id: 会话 ID
            is_error: 是否出错
            cost_usd: 花费

        Returns:
            是否成功
        """
        record = ChatRecord(
            timestamp=datetime.now().timestamp(),
            user_message=user_message,
            agent_response=agent_response,
            session_id=session_id,
            is_error=is_error,
            cost_usd=cost_usd
        )

        records = self._load_user_history(user_id)
        records.append(record.to_dict())
        return self._save_user_history(user_id, records)

    def get_user_history(
        self,
        user_id: int,
        days: Optional[int] = None,
        limit: Optional[int] = None
    ) -> List[ChatRecord]:
        """
        获取用户历史记录

        Args:
            user_id: 用户 ID
            days: 最近多少天（None 表示全部）
            limit: 最多返回多少条（None 表示全部）

        Returns:
            对话记录列表（按时间倒序）
        """
        records = self._load_user_history(user_id)

        # 转换为 ChatRecord 对象
        chat_records = [ChatRecord.from_dict(r) for r in records]

        # 按天筛选
        if days is not None:
            cutoff = (datetime.now() - timedelta(days=days)).timestamp()
            chat_records = [r for r in chat_records if r.timestamp >= cutoff]

        # 按时间倒序
        chat_records.sort(key=lambda x: x.timestamp, reverse=True)

        # 限制数量
        if limit is not None:
            chat_records = chat_records[:limit]

        return chat_records

    def get_daily_stats(
        self,
        user_id: int,
        days: int = 7
    ) -> Dict[str, Dict[str, Any]]:
        """
        获取用户每日统计

        Args:
            user_id: 用户 ID
            days: 统计最近多少天

        Returns:
            {日期: {count: 数量, cost: 花费}}
        """
        records = self._load_user_history(user_id)
        cutoff = (datetime.now() - timedelta(days=days)).timestamp()

        stats: Dict[str, Dict[str, Any]] = {}

        for record in records:
            if record.get('timestamp', 0) < cutoff:
                continue

            date_str = datetime.fromtimestamp(record['timestamp']).strftime('%Y-%m-%d')
            if date_str not in stats:
                stats[date_str] = {'count': 0, 'cost': 0.0, 'errors': 0}

            stats[date_str]['count'] += 1
            stats[date_str]['cost'] += record.get('cost_usd', 0)
            if record.get('is_error', False):
                stats[date_str]['errors'] += 1

        # 补充没有记录的日期
        for i in range(days):
            date = datetime.now() - timedelta(days=i)
            date_str = date.strftime('%Y-%m-%d')
            if date_str not in stats:
                stats[date_str] = {'count': 0, 'cost': 0.0, 'errors': 0}

        return dict(sorted(stats.items(), reverse=True))

    def get_hourly_stats(
        self,
        user_id: int,
        date: Optional[str] = None
    ) -> Dict[int, int]:
        """
        获取用户某天每小时的统计

        Args:
            user_id: 用户 ID
            date: 日期（YYYY-MM-DD 格式，None 表示今天）

        Returns:
            {小时: 数量}
        """
        if date is None:
            date = datetime.now().strftime('%Y-%m-%d')

        records = self._load_user_history(user_id)

        # 按小时统计
        hourly: Dict[int, int] = {h: 0 for h in range(24)}

        for record in records:
            record_date = datetime.fromtimestamp(record.get('timestamp', 0))
            if record_date.strftime('%Y-%m-%d') == date:
                hourly[record_date.hour] += 1

        return hourly

    def get_all_users_stats(self, days: int = 7) -> Dict[int, Dict[str, Any]]:
        """
        获取所有用户的统计

        Args:
            days: 统计最近多少天

        Returns:
            {user_id: {total: 总数, daily_avg: 日均, cost: 总花费}}
        """
        stats = {}

        for history_file in self.history_dir.glob("*.json"):
            try:
                user_id = int(history_file.stem)
                daily = self.get_daily_stats(user_id, days)

                total = sum(d['count'] for d in daily.values())
                cost = sum(d['cost'] for d in daily.values())
                errors = sum(d['errors'] for d in daily.values())

                stats[user_id] = {
                    'total': total,
                    'daily_avg': round(total / days, 1) if days > 0 else 0,
                    'cost': round(cost, 4),
                    'errors': errors
                }
            except Exception as e:
                logger.error(f"统计用户 {history_file.stem} 失败: {e}")

        return stats

    def cleanup_old_records(self, user_id: int, retention_days: int) -> int:
        """
        清理过期记录

        Args:
            user_id: 用户 ID
            retention_days: 保留天数

        Returns:
            删除的记录数
        """
        records = self._load_user_history(user_id)
        original_count = len(records)

        cutoff = (datetime.now() - timedelta(days=retention_days)).timestamp()
        records = [r for r in records if r.get('timestamp', 0) >= cutoff]

        self._save_user_history(user_id, records)
        deleted = original_count - len(records)

        if deleted > 0:
            logger.info(f"清理用户 {user_id} 的 {deleted} 条过期记录")

        return deleted

    def cleanup_all_users(self, get_retention_func) -> Dict[int, int]:
        """
        清理所有用户的过期记录

        Args:
            get_retention_func: 获取用户保留天数的函数 (user_id) -> int

        Returns:
            {user_id: 删除数量}
        """
        results = {}

        for history_file in self.history_dir.glob("*.json"):
            try:
                user_id = int(history_file.stem)
                retention_days = get_retention_func(user_id)
                deleted = self.cleanup_old_records(user_id, retention_days)
                if deleted > 0:
                    results[user_id] = deleted
            except Exception as e:
                logger.error(f"清理用户 {history_file.stem} 失败: {e}")

        return results

    def get_total_records_count(self, user_id: int) -> int:
        """获取用户总记录数"""
        records = self._load_user_history(user_id)
        return len(records)

    def format_record_for_display(self, record: ChatRecord) -> str:
        """格式化记录用于显示"""
        dt = datetime.fromtimestamp(record.timestamp)
        time_str = dt.strftime('%Y-%m-%d %H:%M:%S')

        # 截断过长的消息
        user_msg = record.user_message[:100] + '...' if len(record.user_message) > 100 else record.user_message
        agent_msg = ''
        if record.agent_response:
            agent_msg = record.agent_response[:100] + '...' if len(record.agent_response) > 100 else record.agent_response

        status = '❌' if record.is_error else '✅'

        return f"{status} [{time_str}]\n👤 {user_msg}\n🤖 {agent_msg or '(无回复)'}"
