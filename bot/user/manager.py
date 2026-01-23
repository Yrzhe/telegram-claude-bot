"""用户管理器 - 整合存储和环境管理"""

import json
import logging
from pathlib import Path
from typing import Dict, Optional, Any
from dataclasses import dataclass, asdict

from .storage import StorageManager
from .environment import EnvironmentManager
from .history import HistoryManager

logger = logging.getLogger(__name__)


@dataclass
class UserConfig:
    """用户配置"""
    user_id: int
    quota_bytes: int  # 存储配额
    enabled: bool = True  # 是否启用
    admin: bool = False  # 是否管理员
    notes: str = ""  # 备注（如 "admin", "yumi"）
    retention_days: int = 30  # 对话历史保留天数
    username: str = ""  # Telegram 用户名
    first_name: str = ""  # Telegram 名字

    @classmethod
    def default(cls, user_id: int, default_quota: int, username: str = "", first_name: str = "") -> 'UserConfig':
        return cls(user_id=user_id, quota_bytes=default_quota, username=username, first_name=first_name)


class UserManager:
    """用户管理器"""

    def __init__(
        self,
        base_path: str | Path,
        config_file: str | Path | None = None,
        default_quota_gb: float = 5.0
    ):
        """
        初始化用户管理器

        Args:
            base_path: 用户数据根目录
            config_file: 用户配置文件路径
            default_quota_gb: 默认配额（GB）
        """
        self.base_path = Path(base_path)
        self.base_path.mkdir(parents=True, exist_ok=True)

        self.config_file = Path(config_file) if config_file else self.base_path / "users.json"
        self.default_quota_bytes = int(default_quota_gb * 1024 * 1024 * 1024)

        # 初始化子管理器
        self.storage = StorageManager(self.base_path)
        self.environment = EnvironmentManager(self.base_path)
        self.history = HistoryManager(self.base_path)

        # 用户配置缓存
        self._user_configs: Dict[int, UserConfig] = {}
        self._load_configs()

    def _load_configs(self):
        """加载用户配置"""
        if self.config_file.exists():
            try:
                data = json.loads(self.config_file.read_text(encoding='utf-8'))
                for user_id_str, config_data in data.get("users", {}).items():
                    user_id = int(user_id_str)
                    self._user_configs[user_id] = UserConfig(
                        user_id=user_id,
                        quota_bytes=config_data.get("quota_bytes", self.default_quota_bytes),
                        enabled=config_data.get("enabled", True),
                        admin=config_data.get("admin", False),
                        notes=config_data.get("notes", ""),
                        retention_days=config_data.get("retention_days", 30),
                        username=config_data.get("username", ""),
                        first_name=config_data.get("first_name", "")
                    )
                logger.info(f"加载了 {len(self._user_configs)} 个用户配置")
            except Exception as e:
                logger.error(f"加载用户配置失败: {e}")

    def _save_configs(self):
        """保存用户配置"""
        try:
            data = {
                "users": {
                    str(uid): asdict(config)
                    for uid, config in self._user_configs.items()
                }
            }
            self.config_file.write_text(
                json.dumps(data, indent=2, ensure_ascii=False),
                encoding='utf-8'
            )
        except Exception as e:
            logger.error(f"保存用户配置失败: {e}")

    def user_exists(self, user_id: int) -> bool:
        """
        检查用户是否已存在（不会自动创建）

        Args:
            user_id: 用户 ID

        Returns:
            用户是否存在
        """
        return user_id in self._user_configs

    def get_user_config(self, user_id: int) -> UserConfig:
        """
        获取用户配置，如果不存在则创建默认配置

        Args:
            user_id: 用户 ID

        Returns:
            用户配置
        """
        if user_id not in self._user_configs:
            self._user_configs[user_id] = UserConfig.default(
                user_id, self.default_quota_bytes
            )
            self._save_configs()
        return self._user_configs[user_id]

    def create_user(self, user_id: int, username: str = "", first_name: str = "") -> UserConfig:
        """
        创建新用户配置

        Args:
            user_id: 用户 ID
            username: Telegram 用户名
            first_name: Telegram 名字

        Returns:
            用户配置
        """
        if user_id not in self._user_configs:
            self._user_configs[user_id] = UserConfig.default(
                user_id, self.default_quota_bytes, username, first_name
            )
            self._save_configs()
            logger.info(f"创建新用户: {user_id} (@{username}) {first_name}")
        return self._user_configs[user_id]

    def update_user_info(self, user_id: int, username: str = "", first_name: str = "") -> bool:
        """
        更新用户的 Telegram 信息

        Args:
            user_id: 用户 ID
            username: Telegram 用户名
            first_name: Telegram 名字

        Returns:
            是否有变化（用于判断是否需要刷新 Agent 缓存）
        """
        if user_id in self._user_configs:
            config = self._user_configs[user_id]
            changed = False
            if username and config.username != username:
                config.username = username
                changed = True
            if first_name and config.first_name != first_name:
                config.first_name = first_name
                changed = True
            if changed:
                self._save_configs()
                logger.info(f"用户 {user_id} 信息更新: @{username} {first_name}")
            return changed
        return False

    def set_user_quota(self, user_id: int, quota_gb: float) -> bool:
        """
        设置用户配额

        Args:
            user_id: 用户 ID
            quota_gb: 配额（GB）

        Returns:
            是否成功
        """
        try:
            config = self.get_user_config(user_id)
            config.quota_bytes = int(quota_gb * 1024 * 1024 * 1024)
            self._save_configs()
            logger.info(f"设置用户 {user_id} 配额为 {quota_gb}GB")
            return True
        except Exception as e:
            logger.error(f"设置用户配额失败: {e}")
            return False

    def set_user_enabled(self, user_id: int, enabled: bool) -> bool:
        """启用/禁用用户"""
        try:
            config = self.get_user_config(user_id)
            config.enabled = enabled
            self._save_configs()
            return True
        except Exception:
            return False

    def set_user_admin(self, user_id: int, admin: bool) -> bool:
        """设置用户为管理员"""
        try:
            config = self.get_user_config(user_id)
            config.admin = admin
            self._save_configs()
            return True
        except Exception:
            return False

    def is_user_enabled(self, user_id: int) -> bool:
        """检查用户是否启用"""
        config = self.get_user_config(user_id)
        return config.enabled

    def is_admin(self, user_id: int) -> bool:
        """检查用户是否为管理员"""
        config = self.get_user_config(user_id)
        return config.admin

    def set_user_notes(self, user_id: int, notes: str) -> bool:
        """设置用户备注"""
        try:
            config = self.get_user_config(user_id)
            config.notes = notes
            self._save_configs()
            return True
        except Exception:
            return False

    def set_user_retention(self, user_id: int, days: int) -> bool:
        """设置用户历史保留天数"""
        try:
            config = self.get_user_config(user_id)
            config.retention_days = days
            self._save_configs()
            return True
        except Exception:
            return False

    def get_user_retention(self, user_id: int) -> int:
        """获取用户历史保留天数"""
        config = self.get_user_config(user_id)
        return config.retention_days

    def init_user(self, user_id: int) -> Path:
        """
        初始化用户空间

        Args:
            user_id: 用户 ID

        Returns:
            用户数据目录
        """
        # 确保配置存在
        self.get_user_config(user_id)
        # 初始化存储空间
        return self.storage.init_user_space(user_id)

    def get_user_data_path(self, user_id: int) -> Path:
        """获取用户数据目录"""
        return self.storage.get_user_data_path(user_id)

    def get_user_storage_info(self, user_id: int) -> dict:
        """获取用户存储使用信息"""
        config = self.get_user_config(user_id)
        return self.storage.get_usage_info(user_id, config.quota_bytes)

    def check_user_quota(self, user_id: int, additional_bytes: int) -> tuple[bool, str]:
        """
        检查用户配额

        Args:
            user_id: 用户 ID
            additional_bytes: 需要添加的字节数

        Returns:
            (是否允许, 消息)
        """
        config = self.get_user_config(user_id)
        allowed, used, quota = self.storage.check_quota(
            user_id, additional_bytes, config.quota_bytes
        )

        if allowed:
            return True, "配额充足"
        else:
            used_fmt = self.storage.format_size(used)
            quota_fmt = self.storage.format_size(quota)
            return False, f"配额不足: 已使用 {used_fmt} / {quota_fmt}"

    def get_all_users_info(self) -> list[dict]:
        """获取所有用户信息"""
        users = []
        for user_id, config in self._user_configs.items():
            storage_info = self.storage.get_usage_info(user_id, config.quota_bytes)
            users.append({
                "user_id": user_id,
                "enabled": config.enabled,
                "admin": config.admin,
                "notes": config.notes,
                "retention_days": config.retention_days,
                "storage": storage_info
            })
        return users

    async def create_user_venv(self, user_id: int) -> bool:
        """为用户创建虚拟环境"""
        return await self.environment.create_venv(user_id)

    async def install_user_package(
        self,
        user_id: int,
        package: str
    ) -> tuple[bool, str]:
        """在用户环境中安装包"""
        return await self.environment.install_package(user_id, package)

    async def list_user_packages(self, user_id: int) -> tuple[bool, str]:
        """列出用户环境中的包"""
        return await self.environment.list_packages(user_id)

    def get_user_env_vars(self, user_id: int) -> Dict[str, str]:
        """获取用户环境变量"""
        return self.environment.get_user_env_vars(user_id)

    def set_user_env_var(self, user_id: int, key: str, value: str) -> bool:
        """设置用户环境变量"""
        return self.environment.set_user_env_var(user_id, key, value)

    def delete_user_env_var(self, user_id: int, key: str) -> bool:
        """删除用户环境变量"""
        return self.environment.delete_user_env_var(user_id, key)

    def get_user_full_env(self, user_id: int) -> Dict[str, str]:
        """获取用户完整环境变量"""
        return self.environment.get_full_env(user_id)

    # ===== 历史记录相关方法 =====

    def add_chat_record(
        self,
        user_id: int,
        user_message: str,
        agent_response: Optional[str] = None,
        session_id: Optional[str] = None,
        is_error: bool = False,
        cost_usd: float = 0.0
    ) -> bool:
        """添加对话记录"""
        return self.history.add_record(
            user_id, user_message, agent_response,
            session_id, is_error, cost_usd
        )

    def get_user_chat_history(
        self,
        user_id: int,
        days: Optional[int] = None,
        limit: Optional[int] = None
    ):
        """获取用户对话历史"""
        return self.history.get_user_history(user_id, days, limit)

    def get_user_daily_stats(self, user_id: int, days: int = 7):
        """获取用户每日统计"""
        return self.history.get_daily_stats(user_id, days)

    def get_user_hourly_stats(self, user_id: int, date: Optional[str] = None):
        """获取用户某天每小时统计"""
        return self.history.get_hourly_stats(user_id, date)

    def get_all_users_chat_stats(self, days: int = 7):
        """获取所有用户的对话统计"""
        return self.history.get_all_users_stats(days)

    def cleanup_expired_history(self) -> Dict[int, int]:
        """清理所有用户的过期历史记录"""
        return self.history.cleanup_all_users(self.get_user_retention)

    # ===== 上下文总结相关方法 =====

    def _get_context_summary_file(self, user_id: int) -> Path:
        """获取用户的上下文总结文件路径"""
        user_dir = self.get_user_data_path(user_id)
        return user_dir / ".context_summary.txt"

    def save_context_summary(self, user_id: int, summary: str) -> bool:
        """
        保存上下文总结

        Args:
            user_id: 用户 ID
            summary: 上下文总结内容

        Returns:
            是否成功
        """
        try:
            summary_file = self._get_context_summary_file(user_id)
            summary_file.write_text(summary, encoding='utf-8')
            logger.info(f"保存用户 {user_id} 的上下文总结")
            return True
        except Exception as e:
            logger.error(f"保存上下文总结失败: {e}")
            return False

    def get_context_summary(self, user_id: int) -> Optional[str]:
        """
        获取用户的上下文总结

        Args:
            user_id: 用户 ID

        Returns:
            总结内容，如果没有则返回 None
        """
        try:
            summary_file = self._get_context_summary_file(user_id)
            if summary_file.exists():
                return summary_file.read_text(encoding='utf-8')
            return None
        except Exception as e:
            logger.error(f"读取上下文总结失败: {e}")
            return None

    def clear_context_summary(self, user_id: int) -> bool:
        """
        清除用户的上下文总结

        Args:
            user_id: 用户 ID

        Returns:
            是否成功
        """
        try:
            summary_file = self._get_context_summary_file(user_id)
            if summary_file.exists():
                summary_file.unlink()
                logger.info(f"清除用户 {user_id} 的上下文总结")
            return True
        except Exception as e:
            logger.error(f"清除上下文总结失败: {e}")
            return False
