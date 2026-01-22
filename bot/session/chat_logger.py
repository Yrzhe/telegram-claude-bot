"""对话日志记录器 - 将对话保存到人类可读的 txt 文件"""

import logging
from pathlib import Path
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)


class ChatLogger:
    """将对话记录到 txt 文件，方便人类阅读和检索"""

    def __init__(self, users_base_path: str | Path):
        """
        初始化对话日志记录器

        Args:
            users_base_path: 用户数据根目录
        """
        self.users_base_path = Path(users_base_path)

    def _get_user_chat_logs_dir(self, user_id: int) -> Path:
        """获取用户的对话日志目录"""
        logs_dir = self.users_base_path / str(user_id) / "chat_logs"
        logs_dir.mkdir(parents=True, exist_ok=True)
        return logs_dir

    def _get_user_summaries_dir(self, user_id: int) -> Path:
        """获取用户的对话总结目录"""
        summaries_dir = self.users_base_path / str(user_id) / "chat_summaries"
        summaries_dir.mkdir(parents=True, exist_ok=True)
        return summaries_dir

    def _get_current_log_file(self, user_id: int, session_id: Optional[str] = None) -> Path:
        """获取当前会话的日志文件路径"""
        logs_dir = self._get_user_chat_logs_dir(user_id)

        # 如果有 session_id，使用它作为文件名的一部分
        if session_id:
            # 使用 session_id 的前 8 位
            session_short = session_id[:8] if len(session_id) >= 8 else session_id
            # 查找是否已有该 session 的日志文件
            for f in logs_dir.glob(f"*_{session_short}.txt"):
                return f
            # 创建新文件
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            return logs_dir / f"chat_{timestamp}_{session_short}.txt"
        else:
            # 没有 session_id，使用当前时间
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            return logs_dir / f"chat_{timestamp}_new.txt"

    def log_message(
        self,
        user_id: int,
        user_message: str,
        agent_response: Optional[str] = None,
        session_id: Optional[str] = None,
        is_error: bool = False
    ) -> bool:
        """
        记录一条对话到日志文件

        Args:
            user_id: 用户 ID
            user_message: 用户消息
            agent_response: Agent 回复
            session_id: 会话 ID
            is_error: 是否出错

        Returns:
            是否成功
        """
        try:
            log_file = self._get_current_log_file(user_id, session_id)
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            # 构建日志内容
            log_entry = f"\n{'='*60}\n"
            log_entry += f"[{timestamp}]\n"
            log_entry += f"\n👤 User:\n{user_message}\n"

            if agent_response:
                log_entry += f"\n🤖 Agent:\n{agent_response}\n"
            elif is_error:
                log_entry += f"\n❌ Error: 处理失败\n"

            # 追加到文件
            with open(log_file, 'a', encoding='utf-8') as f:
                # 如果是新文件，添加头部
                if f.tell() == 0 or log_file.stat().st_size == 0:
                    header = f"# 对话记录\n"
                    header += f"# 用户 ID: {user_id}\n"
                    header += f"# 会话 ID: {session_id or 'N/A'}\n"
                    header += f"# 开始时间: {timestamp}\n"
                    f.write(header)
                f.write(log_entry)

            return True
        except Exception as e:
            logger.error(f"记录对话日志失败 (user_id={user_id}): {e}")
            return False

    def get_current_session_log(self, user_id: int, session_id: Optional[str] = None) -> Optional[str]:
        """
        获取当前会话的完整日志内容

        Args:
            user_id: 用户 ID
            session_id: 会话 ID

        Returns:
            日志内容，如果没有则返回 None
        """
        try:
            log_file = self._get_current_log_file(user_id, session_id)
            if log_file.exists():
                return log_file.read_text(encoding='utf-8')
            return None
        except Exception as e:
            logger.error(f"读取对话日志失败: {e}")
            return None

    def get_session_log_by_session_id(self, user_id: int, session_id: str) -> Optional[str]:
        """
        通过 session_id 查找并读取日志

        Args:
            user_id: 用户 ID
            session_id: 会话 ID

        Returns:
            日志内容
        """
        try:
            logs_dir = self._get_user_chat_logs_dir(user_id)
            session_short = session_id[:8] if len(session_id) >= 8 else session_id

            for log_file in logs_dir.glob(f"*_{session_short}.txt"):
                return log_file.read_text(encoding='utf-8')
            return None
        except Exception as e:
            logger.error(f"读取会话日志失败: {e}")
            return None

    def archive_session_log(
        self,
        user_id: int,
        session_id: Optional[str],
        summary: str
    ) -> bool:
        """
        归档当前会话日志并保存总结

        Args:
            user_id: 用户 ID
            session_id: 会话 ID
            summary: 对话总结

        Returns:
            是否成功
        """
        try:
            logs_dir = self._get_user_chat_logs_dir(user_id)
            summaries_dir = self._get_user_summaries_dir(user_id)

            # 查找当前会话的日志文件
            log_file = None
            if session_id:
                session_short = session_id[:8] if len(session_id) >= 8 else session_id
                for f in logs_dir.glob(f"*_{session_short}.txt"):
                    log_file = f
                    break

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

            # 保存总结
            summary_file = summaries_dir / f"summary_{timestamp}.txt"
            summary_content = f"# 对话总结\n"
            summary_content += f"# 时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
            summary_content += f"# 会话 ID: {session_id or 'N/A'}\n"
            summary_content += f"\n{summary}\n"

            # 如果有原始日志，附加到总结文件末尾
            if log_file and log_file.exists():
                original_log = log_file.read_text(encoding='utf-8')
                summary_content += f"\n\n{'='*60}\n"
                summary_content += f"# 原始对话记录\n"
                summary_content += f"{'='*60}\n"
                summary_content += original_log

                # 删除原日志文件（已归档到总结中）
                log_file.unlink()
                logger.info(f"已归档用户 {user_id} 的对话日志: {log_file.name}")

            summary_file.write_text(summary_content, encoding='utf-8')
            logger.info(f"保存对话总结: {summary_file.name}")

            return True
        except Exception as e:
            logger.error(f"归档对话日志失败: {e}")
            return False

    def get_recent_summaries(self, user_id: int, limit: int = 5) -> list[dict]:
        """
        获取用户最近的对话总结

        Args:
            user_id: 用户 ID
            limit: 最多返回多少条

        Returns:
            总结列表 [{filename, timestamp, preview}]
        """
        try:
            summaries_dir = self._get_user_summaries_dir(user_id)
            summaries = []

            # 按修改时间排序
            files = sorted(
                summaries_dir.glob("summary_*.txt"),
                key=lambda f: f.stat().st_mtime,
                reverse=True
            )

            for f in files[:limit]:
                content = f.read_text(encoding='utf-8')
                # 获取预览（前 200 字符）
                lines = content.split('\n')
                # 跳过头部注释，获取正文
                preview_lines = [l for l in lines if not l.startswith('#')]
                preview = '\n'.join(preview_lines)[:200]

                summaries.append({
                    'filename': f.name,
                    'timestamp': datetime.fromtimestamp(f.stat().st_mtime).strftime('%Y-%m-%d %H:%M'),
                    'preview': preview.strip() + '...' if len(preview) > 200 else preview.strip()
                })

            return summaries
        except Exception as e:
            logger.error(f"获取对话总结失败: {e}")
            return []

    def cleanup_old_logs(self, user_id: int, keep_days: int = 30) -> int:
        """
        清理过期的日志文件

        Args:
            user_id: 用户 ID
            keep_days: 保留天数

        Returns:
            删除的文件数
        """
        try:
            from datetime import timedelta

            deleted = 0
            cutoff = datetime.now() - timedelta(days=keep_days)

            # 清理日志文件
            logs_dir = self._get_user_chat_logs_dir(user_id)
            for f in logs_dir.glob("chat_*.txt"):
                if datetime.fromtimestamp(f.stat().st_mtime) < cutoff:
                    f.unlink()
                    deleted += 1

            # 清理总结文件
            summaries_dir = self._get_user_summaries_dir(user_id)
            for f in summaries_dir.glob("summary_*.txt"):
                if datetime.fromtimestamp(f.stat().st_mtime) < cutoff:
                    f.unlink()
                    deleted += 1

            if deleted > 0:
                logger.info(f"清理用户 {user_id} 的 {deleted} 个过期日志文件")

            return deleted
        except Exception as e:
            logger.error(f"清理日志文件失败: {e}")
            return 0
