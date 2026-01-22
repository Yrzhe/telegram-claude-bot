"""Custom command manager for user-specific commands"""

import json
import logging
import random
from pathlib import Path
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Optional, List, Dict, Any

logger = logging.getLogger(__name__)


@dataclass
class CustomCommand:
    """Custom command configuration"""
    name: str  # Command name (without /)
    target_user_id: int  # User who can use this command
    description: str  # Command description shown in /help
    created_by: int  # Admin who created this command
    created_at: str  # ISO timestamp
    command_type: str = "random_media"  # Type: random_media, agent_script
    config: Dict[str, Any] = field(default_factory=dict)
    script: str = ""  # Script/instructions for agent_script type
    # config for random_media:
    #   media_folder: str - folder name for media files
    #   media_type: str - voice, photo, video, document
    #   balance_mode: bool - prioritize least-sent files
    #
    # For agent_script type:
    #   script field contains the execution instructions for Agent

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> 'CustomCommand':
        # Handle backward compatibility for commands without script field
        if 'script' not in data:
            data['script'] = ""
        return cls(**data)


class CustomCommandManager:
    """Manages custom commands for users"""

    def __init__(self, admin_data_path: Path):
        """
        Initialize custom command manager.

        Args:
            admin_data_path: Path to admin user's data directory
        """
        self.admin_data_path = Path(admin_data_path)
        self.commands_dir = self.admin_data_path / "custom_commands"
        self.commands_dir.mkdir(parents=True, exist_ok=True)
        self.config_file = self.commands_dir / "commands.json"
        self._commands: Dict[str, CustomCommand] = {}
        self._load_commands()

    def _load_commands(self):
        """Load commands from config file"""
        if self.config_file.exists():
            try:
                data = json.loads(self.config_file.read_text(encoding='utf-8'))
                for name, cmd_data in data.get("commands", {}).items():
                    self._commands[name] = CustomCommand.from_dict(cmd_data)
                logger.info(f"Loaded {len(self._commands)} custom commands")
            except Exception as e:
                logger.error(f"Failed to load custom commands: {e}")

    def _save_commands(self):
        """Save commands to config file"""
        try:
            data = {
                "commands": {
                    name: cmd.to_dict() for name, cmd in self._commands.items()
                }
            }
            self.config_file.write_text(
                json.dumps(data, indent=2, ensure_ascii=False),
                encoding='utf-8'
            )
        except Exception as e:
            logger.error(f"Failed to save custom commands: {e}")

    def create_command(
        self,
        name: str,
        target_user_id: int,
        description: str,
        created_by: int,
        command_type: str = "random_media",
        config: Dict[str, Any] = None,
        script: str = ""
    ) -> tuple[bool, str]:
        """
        Create a new custom command.

        Args:
            name: Command name (without /)
            target_user_id: User who can use this command
            description: Short description shown in /help
            created_by: Admin who created this
            command_type: "random_media" or "agent_script"
            config: Configuration dict (for random_media type)
            script: Execution script/instructions (for agent_script type)

        Returns:
            (success, message)
        """
        name = name.lower().strip()

        # Validate name
        if not name.isalnum():
            return False, "命令名只能包含字母和数字"
        if len(name) > 20:
            return False, "命令名不能超过20个字符"
        if name in self._commands:
            return False, f"命令 /{name} 已存在"

        # Reserved command names
        reserved = ['start', 'help', 'admin', 'ls', 'del', 'env', 'packages',
                    'schedule', 'skill', 'storage', 'session', 'new', 'cancel']
        if name in reserved:
            return False, f"/{name} 是系统保留命令"

        # Create command
        cmd = CustomCommand(
            name=name,
            target_user_id=target_user_id,
            description=description,
            created_by=created_by,
            created_at=datetime.now().isoformat(),
            command_type=command_type,
            config=config or {},
            script=script
        )

        # Create media folder if random_media type
        if command_type == "random_media":
            media_folder = config.get("media_folder", name) if config else name
            folder_path = self.commands_dir / media_folder
            folder_path.mkdir(parents=True, exist_ok=True)
            cmd.config["media_folder"] = media_folder
            cmd.config.setdefault("media_type", "voice")
            cmd.config.setdefault("balance_mode", True)

        self._commands[name] = cmd
        self._save_commands()
        logger.info(f"Created custom command /{name} (type={command_type}) for user {target_user_id}")
        return True, f"命令 /{name} 创建成功"

    def delete_command(self, name: str) -> tuple[bool, str]:
        """Delete a custom command"""
        name = name.lower().strip()
        if name not in self._commands:
            return False, f"命令 /{name} 不存在"

        cmd = self._commands[name]
        # Note: We don't delete the media folder to preserve files
        del self._commands[name]
        self._save_commands()
        logger.info(f"Deleted custom command /{name}")
        return True, f"命令 /{name} 已删除（媒体文件夹已保留）"

    def rename_command(self, old_name: str, new_name: str) -> tuple[bool, str]:
        """Rename a custom command"""
        old_name = old_name.lower().strip()
        new_name = new_name.lower().strip()

        if old_name not in self._commands:
            return False, f"命令 /{old_name} 不存在"
        if new_name in self._commands:
            return False, f"命令 /{new_name} 已存在"
        if not new_name.isalnum():
            return False, "命令名只能包含字母和数字"

        reserved = ['start', 'help', 'admin', 'ls', 'del', 'env', 'packages',
                    'schedule', 'skill', 'storage', 'session', 'new']
        if new_name in reserved:
            return False, f"/{new_name} 是系统保留命令"

        cmd = self._commands.pop(old_name)
        cmd.name = new_name
        self._commands[new_name] = cmd
        self._save_commands()
        logger.info(f"Renamed command /{old_name} to /{new_name}")
        return True, f"命令已从 /{old_name} 重命名为 /{new_name}"

    def update_command(
        self,
        name: str,
        description: str = None,
        config: Dict[str, Any] = None,
        script: str = None,
        command_type: str = None
    ) -> tuple[bool, str]:
        """Update command description, config, script, or type"""
        name = name.lower().strip()
        if name not in self._commands:
            return False, f"命令 /{name} 不存在"

        cmd = self._commands[name]
        if description is not None:
            cmd.description = description
        if config is not None:
            cmd.config.update(config)
        if script is not None:
            cmd.script = script
        if command_type is not None:
            cmd.command_type = command_type

        self._save_commands()
        logger.info(f"Updated custom command /{name}")
        return True, f"命令 /{name} 已更新"

    def get_command(self, name: str) -> Optional[CustomCommand]:
        """Get a command by name"""
        return self._commands.get(name.lower().strip())

    def get_commands_for_user(self, user_id: int) -> List[CustomCommand]:
        """Get all commands available for a specific user"""
        return [cmd for cmd in self._commands.values() if cmd.target_user_id == user_id]

    def get_all_commands(self) -> List[CustomCommand]:
        """Get all custom commands"""
        return list(self._commands.values())

    def command_exists(self, name: str) -> bool:
        """Check if a command exists"""
        return name.lower().strip() in self._commands

    def get_media_folder(self, name: str) -> Optional[Path]:
        """Get the media folder path for a command"""
        cmd = self.get_command(name)
        if cmd and cmd.command_type == "random_media":
            folder_name = cmd.config.get("media_folder", name)
            return self.commands_dir / folder_name
        return None

    def add_media_file(self, name: str, file_path: Path, filename: str) -> tuple[bool, str]:
        """Add a media file to a command's folder"""
        folder = self.get_media_folder(name)
        if not folder:
            return False, f"命令 /{name} 不存在或不是媒体类型"

        folder.mkdir(parents=True, exist_ok=True)
        dest_path = folder / filename

        try:
            import shutil
            shutil.copy2(file_path, dest_path)
            logger.info(f"Added media file {filename} to command /{name}")
            return True, f"已添加 {filename} 到 /{name}"
        except Exception as e:
            return False, f"添加失败: {e}"

    def get_random_media(self, name: str) -> tuple[Optional[Path], Optional[str]]:
        """
        Get a random media file from command's folder.
        Uses balance mode if enabled (prioritizes least-sent files).

        Returns:
            (file_path, error_message)
        """
        cmd = self.get_command(name)
        if not cmd:
            return None, f"命令 /{name} 不存在"

        folder = self.get_media_folder(name)
        if not folder or not folder.exists():
            return None, "媒体文件夹不存在"

        # Get media files
        media_type = cmd.config.get("media_type", "voice")
        extensions = self._get_extensions_for_type(media_type)
        files = [f for f in folder.iterdir()
                 if f.is_file() and f.suffix.lower() in extensions]

        if not files:
            return None, "文件夹中没有媒体文件"

        # Load stats
        stats_file = folder / "stats.json"
        stats = {}
        if stats_file.exists():
            try:
                stats = json.loads(stats_file.read_text(encoding='utf-8'))
            except Exception:
                pass

        # Balance mode: prioritize least-sent files
        if cmd.config.get("balance_mode", True):
            # Sort by send count (ascending)
            files_with_counts = []
            for f in files:
                count = stats.get(f.name, {}).get("count", 0)
                files_with_counts.append((f, count))

            min_count = min(c for _, c in files_with_counts)
            least_sent = [f for f, c in files_with_counts if c == min_count]
            selected = random.choice(least_sent)
        else:
            selected = random.choice(files)

        # Update stats
        if selected.name not in stats:
            stats[selected.name] = {"count": 0, "last_sent": None}
        stats[selected.name]["count"] += 1
        stats[selected.name]["last_sent"] = datetime.now().isoformat()

        try:
            stats_file.write_text(
                json.dumps(stats, indent=2, ensure_ascii=False),
                encoding='utf-8'
            )
        except Exception as e:
            logger.warning(f"Failed to save stats: {e}")

        return selected, None

    def get_media_stats(self, name: str) -> Optional[Dict[str, Any]]:
        """Get media statistics for a command"""
        folder = self.get_media_folder(name)
        if not folder:
            return None

        stats_file = folder / "stats.json"
        if stats_file.exists():
            try:
                return json.loads(stats_file.read_text(encoding='utf-8'))
            except Exception:
                pass
        return {}

    def list_media_files(self, name: str) -> List[Dict[str, Any]]:
        """List all media files for a command with their stats"""
        cmd = self.get_command(name)
        if not cmd:
            return []

        folder = self.get_media_folder(name)
        if not folder or not folder.exists():
            return []

        media_type = cmd.config.get("media_type", "voice")
        extensions = self._get_extensions_for_type(media_type)
        stats = self.get_media_stats(name) or {}

        result = []
        for f in folder.iterdir():
            if f.is_file() and f.suffix.lower() in extensions:
                file_stats = stats.get(f.name, {})
                result.append({
                    "filename": f.name,
                    "size": f.stat().st_size,
                    "count": file_stats.get("count", 0),
                    "last_sent": file_stats.get("last_sent")
                })

        return sorted(result, key=lambda x: x["count"], reverse=True)

    def _get_extensions_for_type(self, media_type: str) -> set:
        """Get file extensions for a media type"""
        # All common media extensions
        all_extensions = {
            ".ogg", ".mp3", ".m4a", ".wav", ".oga",  # voice/audio
            ".jpg", ".jpeg", ".png", ".gif", ".webp",  # photo
            ".mp4", ".mov", ".avi", ".mkv", ".webm",  # video
            ".pdf", ".doc", ".docx", ".txt", ".xlsx", ".zip"  # document
        }
        type_extensions = {
            "voice": {".ogg", ".mp3", ".m4a", ".wav", ".oga"},
            "photo": {".jpg", ".jpeg", ".png", ".gif", ".webp"},
            "video": {".mp4", ".mov", ".avi", ".mkv", ".webm"},
            "document": all_extensions  # document type accepts ALL file types
        }
        return type_extensions.get(media_type, all_extensions)
