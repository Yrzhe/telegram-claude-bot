"""文件管理器 - 处理文件列表、路径获取和下载"""

import os
from pathlib import Path
from typing import List, Tuple, Optional


class FileManager:
    def __init__(self, base_directory: str, download_directory: str):
        self.base_directory = Path(base_directory).resolve()
        self.download_directory = Path(download_directory).resolve()
        self.download_directory.mkdir(parents=True, exist_ok=True)

    def _is_safe_path(self, path: Path) -> bool:
        """检查路径是否在允许的基础目录内"""
        try:
            resolved = path.resolve()
            return str(resolved).startswith(str(self.base_directory))
        except Exception:
            return False

    def list_directory(self, relative_path: str = "") -> Tuple[bool, str, List[dict]]:
        """
        列出目录内容
        返回: (成功标志, 消息, 文件列表)
        """
        target_path = self.base_directory / relative_path

        if not self._is_safe_path(target_path):
            return False, "访问被拒绝：路径超出允许范围", []

        if not target_path.exists():
            return False, f"路径不存在: {relative_path}", []

        if not target_path.is_dir():
            return False, f"不是目录: {relative_path}", []

        items = []
        try:
            for item in sorted(target_path.iterdir()):
                item_info = {
                    "name": item.name,
                    "is_dir": item.is_dir(),
                    "size": item.stat().st_size if item.is_file() else 0,
                    "path": str(item.relative_to(self.base_directory))
                }
                items.append(item_info)

            return True, f"目录: /{relative_path}" if relative_path else "目录: /", items
        except PermissionError:
            return False, "权限不足，无法读取目录", []

    def get_file_info(self, relative_path: str) -> Tuple[bool, str, Optional[dict]]:
        """
        获取文件信息
        返回: (成功标志, 消息, 文件信息)
        """
        target_path = self.base_directory / relative_path

        if not self._is_safe_path(target_path):
            return False, "访问被拒绝：路径超出允许范围", None

        if not target_path.exists():
            return False, f"文件不存在: {relative_path}", None

        try:
            stat = target_path.stat()
            info = {
                "name": target_path.name,
                "path": str(target_path),
                "relative_path": relative_path,
                "size": stat.st_size,
                "is_dir": target_path.is_dir(),
                "readable": os.access(target_path, os.R_OK)
            }
            return True, "文件信息获取成功", info
        except Exception as e:
            return False, f"获取文件信息失败: {str(e)}", None

    def get_file_path(self, relative_path: str) -> Tuple[bool, str, Optional[str]]:
        """
        获取文件的完整路径
        返回: (成功标志, 消息, 完整路径)
        """
        target_path = self.base_directory / relative_path

        if not self._is_safe_path(target_path):
            return False, "访问被拒绝：路径超出允许范围", None

        if not target_path.exists():
            return False, f"文件不存在: {relative_path}", None

        return True, "路径获取成功", str(target_path.resolve())

    def format_size(self, size: int) -> str:
        """格式化文件大小"""
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if size < 1024:
                return f"{size:.1f} {unit}"
            size /= 1024
        return f"{size:.1f} PB"
