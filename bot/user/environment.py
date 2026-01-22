"""用户环境隔离管理"""

import os
import sys
import asyncio
import logging
from pathlib import Path
from typing import Dict, Optional

logger = logging.getLogger(__name__)


class EnvironmentManager:
    """管理用户独立的运行环境（虚拟环境 + 环境变量）"""

    def __init__(self, base_path: Path):
        """
        初始化环境管理器

        Args:
            base_path: 用户数据根目录
        """
        self.base_path = base_path

    def get_user_venv_path(self, user_id: int) -> Path:
        """获取用户虚拟环境路径"""
        return self.base_path / str(user_id) / "venv"

    def get_user_env_file(self, user_id: int) -> Path:
        """获取用户环境变量文件"""
        return self.base_path / str(user_id) / ".env"

    def parse_env_file(self, env_file: Path) -> Dict[str, str]:
        """
        解析 .env 文件

        Args:
            env_file: .env 文件路径

        Returns:
            环境变量字典
        """
        env_vars = {}
        if not env_file.exists():
            return env_vars

        try:
            content = env_file.read_text(encoding='utf-8')
            for line in content.splitlines():
                line = line.strip()
                # 跳过空行和注释
                if not line or line.startswith('#'):
                    continue
                # 解析 KEY=VALUE
                if '=' in line:
                    key, _, value = line.partition('=')
                    key = key.strip()
                    value = value.strip()
                    # 移除引号
                    if value and value[0] in ('"', "'") and value[-1] == value[0]:
                        value = value[1:-1]
                    env_vars[key] = value
        except Exception as e:
            logger.warning(f"解析环境变量文件失败: {e}")

        return env_vars

    def get_user_env_vars(self, user_id: int) -> Dict[str, str]:
        """
        获取用户的环境变量

        Args:
            user_id: 用户 ID

        Returns:
            环境变量字典
        """
        env_file = self.get_user_env_file(user_id)
        return self.parse_env_file(env_file)

    def set_user_env_var(self, user_id: int, key: str, value: str) -> bool:
        """
        设置用户环境变量

        Args:
            user_id: 用户 ID
            key: 变量名
            value: 变量值

        Returns:
            是否成功
        """
        try:
            env_file = self.get_user_env_file(user_id)
            env_vars = self.parse_env_file(env_file)
            env_vars[key] = value

            # 写回文件
            lines = ["# 用户环境变量", "# 格式: KEY=VALUE", ""]
            for k, v in sorted(env_vars.items()):
                # 如果值包含空格或特殊字符，使用引号
                if ' ' in v or '"' in v or "'" in v:
                    v = f'"{v}"'
                lines.append(f"{k}={v}")

            env_file.write_text('\n'.join(lines) + '\n', encoding='utf-8')
            return True
        except Exception as e:
            logger.error(f"设置环境变量失败: {e}")
            return False

    def delete_user_env_var(self, user_id: int, key: str) -> bool:
        """
        删除用户环境变量

        Args:
            user_id: 用户 ID
            key: 变量名

        Returns:
            是否成功
        """
        try:
            env_file = self.get_user_env_file(user_id)
            env_vars = self.parse_env_file(env_file)

            if key in env_vars:
                del env_vars[key]

                # 写回文件
                lines = ["# 用户环境变量", "# 格式: KEY=VALUE", ""]
                for k, v in sorted(env_vars.items()):
                    if ' ' in v or '"' in v or "'" in v:
                        v = f'"{v}"'
                    lines.append(f"{k}={v}")

                env_file.write_text('\n'.join(lines) + '\n', encoding='utf-8')

            return True
        except Exception as e:
            logger.error(f"删除环境变量失败: {e}")
            return False

    async def create_venv(self, user_id: int) -> bool:
        """
        为用户创建虚拟环境

        Args:
            user_id: 用户 ID

        Returns:
            是否成功
        """
        venv_path = self.get_user_venv_path(user_id)

        if venv_path.exists():
            return True

        try:
            # 使用 venv 模块创建虚拟环境
            process = await asyncio.create_subprocess_exec(
                sys.executable, '-m', 'venv', str(venv_path),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            _, stderr = await process.communicate()

            if process.returncode != 0:
                logger.error(f"创建虚拟环境失败: {stderr.decode()}")
                return False

            logger.info(f"为用户 {user_id} 创建虚拟环境: {venv_path}")
            return True
        except Exception as e:
            logger.error(f"创建虚拟环境异常: {e}")
            return False

    def get_venv_python(self, user_id: int) -> Optional[str]:
        """
        获取用户虚拟环境的 Python 解释器路径

        Args:
            user_id: 用户 ID

        Returns:
            Python 路径，如果不存在返回 None
        """
        venv_path = self.get_user_venv_path(user_id)
        python_path = venv_path / "bin" / "python"

        if python_path.exists():
            return str(python_path)
        return None

    def get_venv_pip(self, user_id: int) -> Optional[str]:
        """
        获取用户虚拟环境的 pip 路径

        Args:
            user_id: 用户 ID

        Returns:
            pip 路径，如果不存在返回 None
        """
        venv_path = self.get_user_venv_path(user_id)
        pip_path = venv_path / "bin" / "pip"

        if pip_path.exists():
            return str(pip_path)
        return None

    async def install_package(
        self,
        user_id: int,
        package: str,
        timeout: int = 120
    ) -> tuple[bool, str]:
        """
        在用户虚拟环境中安装包

        Args:
            user_id: 用户 ID
            package: 包名
            timeout: 超时时间（秒）

        Returns:
            (是否成功, 输出信息)
        """
        pip_path = self.get_venv_pip(user_id)

        if not pip_path:
            # 尝试创建虚拟环境
            created = await self.create_venv(user_id)
            if not created:
                return False, "虚拟环境创建失败"
            pip_path = self.get_venv_pip(user_id)

        try:
            process = await asyncio.create_subprocess_exec(
                pip_path, 'install', package,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=timeout
            )

            output = stdout.decode() + stderr.decode()

            if process.returncode == 0:
                return True, f"成功安装 {package}"
            else:
                return False, f"安装失败: {output}"
        except asyncio.TimeoutError:
            return False, f"安装超时（{timeout}秒）"
        except Exception as e:
            return False, f"安装异常: {str(e)}"

    async def list_packages(self, user_id: int) -> tuple[bool, str]:
        """
        列出用户虚拟环境中的包

        Args:
            user_id: 用户 ID

        Returns:
            (是否成功, 包列表或错误信息)
        """
        pip_path = self.get_venv_pip(user_id)

        if not pip_path:
            return False, "虚拟环境不存在"

        try:
            process = await asyncio.create_subprocess_exec(
                pip_path, 'list', '--format=freeze',
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, _ = await process.communicate()

            if process.returncode == 0:
                return True, stdout.decode()
            else:
                return False, "获取包列表失败"
        except Exception as e:
            return False, f"异常: {str(e)}"

    def get_full_env(self, user_id: int) -> Dict[str, str]:
        """
        获取用户的完整环境变量（系统 + 用户自定义）

        Args:
            user_id: 用户 ID

        Returns:
            完整环境变量字典
        """
        # 从系统环境开始
        env = os.environ.copy()

        # 添加用户自定义环境变量
        user_env = self.get_user_env_vars(user_id)
        env.update(user_env)

        # 设置虚拟环境相关
        venv_path = self.get_user_venv_path(user_id)
        if venv_path.exists():
            env['VIRTUAL_ENV'] = str(venv_path)
            env['PATH'] = f"{venv_path}/bin:{env.get('PATH', '')}"

        return env
