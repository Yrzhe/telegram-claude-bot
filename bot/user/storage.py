"""用户存储配额管理"""

import os
import shutil
from pathlib import Path
from typing import Tuple


class StorageManager:
    """管理用户存储空间和配额"""

    # 默认配额 5GB
    DEFAULT_QUOTA_BYTES = 5 * 1024 * 1024 * 1024

    def __init__(self, base_path: Path):
        """
        初始化存储管理器

        Args:
            base_path: 用户数据根目录
        """
        self.base_path = base_path

    def get_user_path(self, user_id: int) -> Path:
        """获取用户根目录"""
        return self.base_path / str(user_id)

    def get_user_data_path(self, user_id: int) -> Path:
        """获取用户数据目录"""
        return self.get_user_path(user_id) / "data"

    def get_user_venv_path(self, user_id: int) -> Path:
        """获取用户虚拟环境目录"""
        return self.get_user_path(user_id) / "venv"

    def get_user_env_file(self, user_id: int) -> Path:
        """获取用户环境变量文件"""
        return self.get_user_path(user_id) / ".env"

    def init_user_space(self, user_id: int) -> Path:
        """
        初始化用户空间

        Args:
            user_id: 用户 ID

        Returns:
            用户数据目录路径
        """
        user_path = self.get_user_path(user_id)
        data_path = self.get_user_data_path(user_id)

        # 创建目录结构
        data_path.mkdir(parents=True, exist_ok=True)

        # 创建空的 .env 文件（如果不存在）
        env_file = self.get_user_env_file(user_id)
        if not env_file.exists():
            env_file.write_text("# 用户环境变量\n# 格式: KEY=VALUE\n")

        return data_path

    def get_directory_size(self, path: Path) -> int:
        """
        计算目录大小（字节）

        Args:
            path: 目录路径

        Returns:
            目录总大小（字节）
        """
        total_size = 0
        if not path.exists():
            return 0

        for dirpath, dirnames, filenames in os.walk(path):
            for filename in filenames:
                filepath = Path(dirpath) / filename
                try:
                    total_size += filepath.stat().st_size
                except (OSError, FileNotFoundError):
                    pass
        return total_size

    def get_user_usage(self, user_id: int) -> int:
        """
        获取用户已使用的存储空间

        Args:
            user_id: 用户 ID

        Returns:
            已使用空间（字节）
        """
        user_path = self.get_user_path(user_id)
        return self.get_directory_size(user_path)

    def check_quota(
        self,
        user_id: int,
        additional_bytes: int,
        quota_bytes: int | None = None
    ) -> Tuple[bool, int, int]:
        """
        检查用户是否有足够配额

        Args:
            user_id: 用户 ID
            additional_bytes: 需要添加的字节数
            quota_bytes: 用户配额（None 使用默认值）

        Returns:
            (是否允许, 当前使用量, 配额上限)
        """
        quota = quota_bytes if quota_bytes is not None else self.DEFAULT_QUOTA_BYTES
        current_usage = self.get_user_usage(user_id)

        allowed = (current_usage + additional_bytes) <= quota
        return allowed, current_usage, quota

    def format_size(self, size_bytes: int) -> str:
        """格式化文件大小"""
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if size_bytes < 1024:
                return f"{size_bytes:.2f} {unit}"
            size_bytes /= 1024
        return f"{size_bytes:.2f} PB"

    def get_usage_info(self, user_id: int, quota_bytes: int | None = None) -> dict:
        """
        获取用户存储使用信息

        Args:
            user_id: 用户 ID
            quota_bytes: 用户配额

        Returns:
            使用信息字典
        """
        quota = quota_bytes if quota_bytes is not None else self.DEFAULT_QUOTA_BYTES
        used = self.get_user_usage(user_id)
        available = max(0, quota - used)
        percentage = (used / quota * 100) if quota > 0 else 0

        return {
            "used_bytes": used,
            "quota_bytes": quota,
            "available_bytes": available,
            "used_formatted": self.format_size(used),
            "quota_formatted": self.format_size(quota),
            "available_formatted": self.format_size(available),
            "percentage": round(percentage, 2)
        }

    def cleanup_user_space(self, user_id: int, keep_env: bool = True) -> bool:
        """
        清理用户空间

        Args:
            user_id: 用户 ID
            keep_env: 是否保留环境变量文件

        Returns:
            是否成功
        """
        try:
            user_path = self.get_user_path(user_id)
            if not user_path.exists():
                return True

            if keep_env:
                # 保留 .env 文件，删除其他
                env_file = self.get_user_env_file(user_id)
                env_content = env_file.read_text() if env_file.exists() else ""

                shutil.rmtree(user_path)
                self.init_user_space(user_id)

                if env_content:
                    env_file.write_text(env_content)
            else:
                shutil.rmtree(user_path)

            return True
        except Exception:
            return False
