#!/usr/bin/env python3
"""Telegram 文件管理 Bot 入口"""

import asyncio
import json
import logging
from pathlib import Path
from datetime import time, datetime
from typing import Dict, Optional
from telegram.ext import Application

from bot import setup_handlers, UserManager, SessionManager
from bot.schedule import ScheduleManager
from bot.skill import SkillManager
from bot.agent.task_manager import TaskManager


def load_config(config_path: str = "config.json") -> dict:
    """加载配置文件"""
    config_file = Path(config_path)
    if not config_file.exists():
        raise FileNotFoundError(f"配置文件不存在: {config_path}")

    with open(config_file, 'r', encoding='utf-8') as f:
        return json.load(f)


# Global task managers cache
_task_managers: Dict[int, TaskManager] = {}


def get_or_create_task_manager(
    user_id: int,
    user_manager: UserManager,
    on_task_complete=None,
    send_file_callback=None,
    send_message_callback=None
) -> TaskManager:
    """Get or create TaskManager for a user."""
    if user_id not in _task_managers:
        user_dir = str(user_manager.get_user_data_path(user_id).parent)
        _task_managers[user_id] = TaskManager(
            user_id=user_id,
            working_directory=user_dir,
            on_task_complete=on_task_complete,
            send_file_callback=send_file_callback,
            send_message_callback=send_message_callback
        )
    return _task_managers[user_id]


async def run_api_server(
    user_manager: UserManager,
    session_manager: SessionManager,
    schedule_manager: ScheduleManager,
    bot_token: str,
    allow_new_users: bool,
    host: str = "127.0.0.1",
    port: int = 8000,
    dev_mode: bool = False,
    skill_manager=None,
    api_config: dict = None
):
    """Run the Mini App API server."""
    try:
        from api.server import create_api_app
        from api.websocket import ws_manager
        import uvicorn

        logger = logging.getLogger(__name__)

        # Create task manager factory that integrates with WebSocket
        def get_task_manager(user_id: int) -> TaskManager:
            async def notify_complete(task_id, description, result):
                await ws_manager.broadcast_task_update(user_id, task_id, "completed", result)

            return get_or_create_task_manager(
                user_id=user_id,
                user_manager=user_manager,
                on_task_complete=notify_complete
            )

        # Create API app
        api_app = create_api_app(
            user_manager=user_manager,
            session_manager=session_manager,
            schedule_manager=schedule_manager,
            get_task_manager=get_task_manager,
            bot_token=bot_token,
            allow_new_users=allow_new_users,
            dev_mode=dev_mode,
            skill_manager=skill_manager,
            api_config=api_config
        )

        # Configure uvicorn
        config = uvicorn.Config(
            api_app,
            host=host,
            port=port,
            log_level="info",
            access_log=False
        )
        server = uvicorn.Server(config)

        logger.info(f"Starting Mini App API server on {host}:{port}")
        await server.serve()

    except ImportError as e:
        logger = logging.getLogger(__name__)
        logger.warning(f"API server dependencies not available: {e}")
        logger.warning("Mini App API will not be available. Install with: pip install fastapi uvicorn python-jose")
    except Exception as e:
        logger = logging.getLogger(__name__)
        logger.error(f"Failed to start API server: {e}")


def _save_scheduled_notification(user_data_path: Path, task_name: str, task_id: str, result_text: str):
    """Save a notification record so main agent has context for future conversations."""
    import json as _json
    logger = logging.getLogger(__name__)

    notif_dir = user_data_path / "data"
    notif_dir.mkdir(parents=True, exist_ok=True)
    notif_file = notif_dir / "scheduled_notifications.jsonl"

    entry = {
        "task_id": task_id,
        "task_name": task_name,
        "completed_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "summary": result_text
    }

    try:
        # Append new entry
        with open(notif_file, 'a', encoding='utf-8') as f:
            f.write(_json.dumps(entry, ensure_ascii=False) + "\n")

        # Keep only the last 20 entries
        lines = notif_file.read_text(encoding='utf-8').strip().split('\n')
        if len(lines) > 20:
            with open(notif_file, 'w', encoding='utf-8') as f:
                f.write('\n'.join(lines[-20:]) + '\n')
    except Exception as e:
        logger.error(f"Failed to save scheduled notification: {e}")


def _load_scheduled_notifications(user_data_path: Path, max_count: int = 5) -> list[dict]:
    """Load recent scheduled task notifications for main agent context."""
    import json as _json

    notif_file = user_data_path / "data" / "scheduled_notifications.jsonl"
    if not notif_file.exists():
        return []

    try:
        lines = notif_file.read_text(encoding='utf-8').strip().split('\n')
        notifications = []
        for line in lines[-max_count:]:
            line = line.strip()
            if line:
                notifications.append(_json.loads(line))
        return notifications
    except Exception:
        return []


async def _deliver_via_main_agent(
    app: Application,
    user_id: int,
    task_name: str,
    task_id: str,
    result_text: str,
    user_manager: UserManager,
    api_config: dict,
    files_sent: int = 0
):
    """Deliver scheduled task result through the main agent instead of directly."""
    from bot.agent import TelegramAgentClient
    from bot.message_queue import MessageQueueManager

    logger = logging.getLogger(__name__)
    user_data_path = user_manager.get_user_data_path(user_id)

    # Create a message queue manager for this delivery
    msg_queue = MessageQueueManager(app.bot)
    send_msg, send_file, send_buttons = msg_queue.get_callbacks(user_id, user_data_path)

    # Prepare environment variables
    env_vars = user_manager.get_user_env_vars(user_id)
    agent_env_vars = env_vars.copy()
    if api_config.get("api_key"):
        agent_env_vars["ANTHROPIC_API_KEY"] = api_config["api_key"]
    if api_config.get("base_url"):
        agent_env_vars["ANTHROPIC_BASE_URL"] = api_config["base_url"]

    # Create main agent with message-sending capability
    agent = TelegramAgentClient(
        user_id=user_id,
        working_directory=str(user_data_path),
        send_message_callback=send_msg,
        send_file_callback=send_file,
        send_buttons_callback=send_buttons,
        env_vars=agent_env_vars,
        model=api_config.get("model"),
        max_turns=5  # Short limit — just review and deliver
    )

    # Build delivery prompt
    files_note = ""
    if files_sent > 0:
        files_note = f"\n\nNote: {files_sent} file(s) generated by this task have already been sent to the user."

    delivery_system_prompt = f"""You are delivering a scheduled task result to the user.

RULES:
1. Use send_telegram_message to deliver the result to the user
2. Start with "⏰ {task_name}" as a header so the user knows this is a scheduled task result
3. Present the result clearly. Reformat for readability if needed, but do NOT omit any information
4. If the result is very long, summarize key points and include the full details
5. Keep your response concise — you are just a messenger
6. NEVER show full system paths like /app/users/xxx
7. Respond in the same language as the task result"""

    prompt = f"""[Scheduled Task Completed]
Task: {task_name} (ID: {task_id})

Below is the sub-agent's result. Review and send to the user via send_telegram_message.
{files_note}

---
{result_text}
---"""

    try:
        response = await agent.process_message(
            prompt,
            custom_system_prompt=delivery_system_prompt,
            track_files=False
        )

        # If main agent didn't send via tool, send its response text as fallback
        if response.text and not response.message_sent:
            await send_msg(response.text)

        logger.info(f"Scheduled task {task_id} result delivered via main agent for user {user_id}")

    except Exception as e:
        logger.error(f"Main agent delivery failed for task {task_id}, falling back to direct send: {e}")
        # Fallback: send directly if main agent fails
        from bot.agent.tools import convert_to_markdown_v2
        fallback_text = f"⏰ {task_name}\n\n{result_text}"
        if len(fallback_text) > 3000:
            fallback_text = fallback_text[:3000] + "... (truncated)"
        try:
            formatted = convert_to_markdown_v2(fallback_text)
            await app.bot.send_message(chat_id=user_id, text=formatted, parse_mode="MarkdownV2")
        except Exception:
            await app.bot.send_message(chat_id=user_id, text=fallback_text)

    # Save notification for future main agent context
    _save_scheduled_notification(user_data_path, task_name, task_id, result_text)


async def main_async():
    """异步主函数"""
    # 设置日志
    logging.basicConfig(
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        level=logging.INFO
    )
    logger = logging.getLogger(__name__)

    # 加载配置
    try:
        config = load_config()
    except FileNotFoundError as e:
        logger.error(str(e))
        return
    except json.JSONDecodeError as e:
        logger.error(f"配置文件格式错误: {e}")
        return

    bot_token = config.get("bot_token", "")
    if not bot_token or bot_token == "YOUR_BOT_TOKEN_HERE":
        logger.error("请在 config.json 中设置有效的 bot_token")
        return

    # 初始化用户管理器
    users_data_dir = config.get("users_data_directory", "/root/telegram bot/users")
    default_quota_gb = config.get("default_quota_gb", 5.0)

    user_manager = UserManager(
        base_path=users_data_dir,
        default_quota_gb=default_quota_gb
    )

    # 初始化会话管理器
    sessions_file = Path(users_data_dir) / "sessions.json"
    session_timeout = config.get("session_timeout_minutes", 30) * 60  # 转换为秒

    session_manager = SessionManager(
        sessions_file=sessions_file,
        session_timeout=session_timeout
    )

    # 初始化定时任务管理器
    schedule_manager = ScheduleManager(users_base_path=users_data_dir)

    # 初始化技能管理器
    system_skills_dir = str(Path(__file__).parent / ".claude" / "skills")
    skill_manager = SkillManager(users_base_path=users_data_dir, system_skills_path=system_skills_dir)

    # 创建 Bot 应用
    app = Application.builder().token(bot_token).build()

    # 设置命令处理器
    admin_users = config.get("admin_users", [])
    allow_new_users = config.get("allow_new_users", True)

    # API 配置
    api_config = {
        "api_key": config.get("anthropic_api_key", ""),
        "base_url": config.get("anthropic_base_url", ""),
        "model": config.get("claude_model", ""),
        "mistral_api_key": config.get("mistral_api_key", ""),
        "openai_api_key": config.get("openai_api_key", "")
    }

    setup_handlers(
        app=app,
        user_manager=user_manager,
        session_manager=session_manager,
        admin_users=admin_users,
        allow_new_users=allow_new_users,
        api_config=api_config,
        schedule_manager=schedule_manager,
        skill_manager=skill_manager,
        mini_app_url=config.get("mini_app_url", "")
    )

    # 设置定时任务管理器
    job_queue = app.job_queue
    if job_queue:
        schedule_manager.set_job_queue(job_queue)

        # 创建定时任务执行回调
        async def execute_scheduled_task(user_id: int, task_id: str, prompt: str):
            """Execute a scheduled task via Sub Agent"""
            import shutil
            from datetime import datetime
            from bot.agent import create_sub_agent
            from bot.file_tracker import FileTracker, send_tracked_files

            user_data_path = user_manager.get_user_data_path(user_id)
            env_vars = user_manager.get_user_env_vars(user_id)

            # Ensure user's custom skills are accessible via Skill tool
            if skill_manager:
                skill_manager.setup_skill_symlinks(user_id, user_data_path)

            # Add API config to env vars
            agent_env_vars = env_vars.copy()
            if api_config.get("api_key"):
                agent_env_vars["ANTHROPIC_API_KEY"] = api_config["api_key"]
            if api_config.get("base_url"):
                agent_env_vars["ANTHROPIC_BASE_URL"] = api_config["base_url"]

            # Send file callback
            async def send_file(file_path: str, caption: str | None) -> bool:
                full_path = user_data_path / file_path
                if not full_path.exists():
                    full_path = Path(file_path)
                    if not full_path.exists():
                        return False
                if full_path.stat().st_size > 50 * 1024 * 1024:
                    return False
                try:
                    await app.bot.send_document(
                        chat_id=user_id,
                        document=open(full_path, 'rb'),
                        caption=caption
                    )
                    return True
                except Exception as e:
                    logger.error(f"Failed to send file for scheduled task: {e}")
                    return False

            # Get task info
            task = schedule_manager.get_task(user_id, task_id)
            task_name = task.name if task else task_id
            start_time = datetime.now()

            # Create task document in running_tasks
            running_dir = user_data_path / "data" / "running_tasks"
            completed_dir = user_data_path / "data" / "completed_tasks"
            running_dir.mkdir(parents=True, exist_ok=True)
            completed_dir.mkdir(parents=True, exist_ok=True)

            doc_filename = f"schedule_{task_id}_{start_time.strftime('%Y%m%d_%H%M%S')}.md"
            doc_path = running_dir / doc_filename

            doc_content = f"""# Scheduled Task: {task_name}

**Task ID:** {task_id}
**Type:** Scheduled Task
**Started:** {start_time.strftime('%Y-%m-%d %H:%M:%S')}
**Status:** running

## Task Instructions

{prompt}

## Progress

_Task is running..._
"""
            try:
                with open(doc_path, 'w', encoding='utf-8') as f:
                    f.write(doc_content)
            except Exception as e:
                logger.error(f"Failed to create scheduled task document: {e}")

            # Notify user that scheduled task is starting
            try:
                await app.bot.send_message(
                    chat_id=user_id,
                    text=f"⏰ Running scheduled task: {task_name}"
                )
            except Exception as e:
                logger.error(f"Failed to notify user {user_id} of scheduled task start: {e}")

            # Start file tracking before task execution
            file_tracker = FileTracker(user_data_path)
            file_tracker.start()

            # Create and run Sub Agent
            sub_agent = create_sub_agent(
                user_id=user_id,
                working_directory=str(user_data_path),
                env_vars=agent_env_vars,
                model=api_config.get("model"),
                mistral_api_key=api_config.get("mistral_api_key"),
                send_file_callback=send_file
            )

            # Get custom skills catalog for the scheduled task agent
            custom_skills_text = ""
            if skill_manager:
                custom_skills_text = skill_manager.get_skills_for_agent(user_id)

            sub_system_prompt = f"""You are executing a scheduled task: {task_name}

RULES:
1. Complete the task independently
2. Any files you create will be AUTOMATICALLY sent to the user by the system - just create the file, no need to send it manually
3. NEVER show full system paths like /app/users/xxx - use relative paths only
4. Your final response will be shown to the user as the task completion message - keep it concise and informative
5. Be efficient and complete the task without unnecessary steps
6. If the task involves reminding about specific items (commands, links, etc.), ALWAYS include those specific details in your response
{custom_skills_text}
Task instructions:
{prompt}
"""

            try:
                response = await sub_agent.process_message(
                    prompt,
                    custom_system_prompt=sub_system_prompt
                )

                # Deliver result via main agent (not direct to user)
                result_text = response.text or "Task completed"

                # Send tracked files before delivery (so main agent can reference them)
                tracked_files_sent = 0
                try:
                    new_files = file_tracker.get_new_files()
                    if new_files:
                        tracked_files_sent = await send_tracked_files(
                            files=new_files,
                            working_dir=user_data_path,
                            send_file_callback=send_file
                        )
                        if tracked_files_sent > 0:
                            logger.info(f"Scheduled task {task_id}: Sent {tracked_files_sent} new files to user {user_id}")
                except Exception as e:
                    logger.error(f"Failed to send tracked files for scheduled task: {e}")

                # Route through main agent for formatting and delivery
                await _deliver_via_main_agent(
                    app=app,
                    user_id=user_id,
                    task_name=task_name,
                    task_id=task_id,
                    result_text=result_text,
                    user_manager=user_manager,
                    api_config=api_config,
                    files_sent=tracked_files_sent
                )

                # Update and move task document to completed_tasks
                end_time = datetime.now()
                result_for_doc = response.text or "Task completed"
                if len(result_for_doc) > 5000:
                    result_for_doc = result_for_doc[:5000] + "\n\n... (truncated)"

                doc_update = f"""# Scheduled Task: {task_name}

**Task ID:** {task_id}
**Type:** Scheduled Task
**Started:** {start_time.strftime('%Y-%m-%d %H:%M:%S')}
**Completed:** {end_time.strftime('%Y-%m-%d %H:%M:%S')}
**Status:** completed

## Task Instructions

{prompt}

## Result

{result_for_doc}
"""
                try:
                    with open(doc_path, 'w', encoding='utf-8') as f:
                        f.write(doc_update)
                    shutil.move(str(doc_path), str(completed_dir / doc_filename))
                except Exception as e:
                    logger.error(f"Failed to update scheduled task document: {e}")

            except Exception as e:
                logger.error(f"Scheduled task {task_id} for user {user_id} failed: {e}")

                # Update task document with error
                end_time = datetime.now()
                doc_update = f"""# Scheduled Task: {task_name}

**Task ID:** {task_id}
**Type:** Scheduled Task
**Started:** {start_time.strftime('%Y-%m-%d %H:%M:%S')}
**Failed:** {end_time.strftime('%Y-%m-%d %H:%M:%S')}
**Status:** failed

## Task Instructions

{prompt}

## Error

{str(e)}
"""
                try:
                    with open(doc_path, 'w', encoding='utf-8') as f:
                        f.write(doc_update)
                    shutil.move(str(doc_path), str(completed_dir / doc_filename))
                except Exception as doc_e:
                    logger.error(f"Failed to update scheduled task document: {doc_e}")

                try:
                    await app.bot.send_message(
                        chat_id=user_id,
                        text=f"❌ Scheduled task failed: {task_name}\n\nError: {str(e)}"
                    )
                except Exception:
                    pass

        schedule_manager.set_execute_callback(execute_scheduled_task)

        # Initialize all schedules on startup
        schedule_manager.initialize_all_schedules()
        logger.info("定时任务管理器已初始化")

    # 定时清理过期历史记录（每天凌晨 3 点执行）
    async def cleanup_job(context):
        logger.info("开始清理过期历史记录...")
        results = user_manager.cleanup_expired_history()
        if results:
            for uid, count in results.items():
                logger.info(f"用户 {uid} 清理了 {count} 条过期记录")

        # 清理过期的任务文档（超过 7 天的 completed_tasks）
        logger.info("开始清理过期任务文档...")
        users_path = Path(users_data_dir)
        if users_path.exists():
            from datetime import datetime
            now = datetime.now()
            total_cleaned = 0
            for user_dir in users_path.iterdir():
                if not user_dir.is_dir():
                    continue
                completed_dir = user_dir / "data" / "completed_tasks"
                if completed_dir.exists():
                    for doc in completed_dir.glob("*.md"):
                        try:
                            mtime = datetime.fromtimestamp(doc.stat().st_mtime)
                            if (now - mtime).days > 7:
                                doc.unlink()
                                total_cleaned += 1
                        except Exception as e:
                            logger.error(f"清理任务文档失败 {doc}: {e}")
            if total_cleaned > 0:
                logger.info(f"清理了 {total_cleaned} 个过期任务文档")

            # Clean up old voice files (older than 24 hours)
            logger.info("开始清理过期语音文件...")
            from bot.transcribe import TranscriptManager
            voice_cleaned = 0
            for user_dir in users_path.iterdir():
                if not user_dir.is_dir():
                    continue
                try:
                    transcript_manager = TranscriptManager(user_dir)
                    transcript_manager.cleanup_old_voice_files(max_age_hours=24)
                    voice_cleaned += 1
                except Exception as e:
                    logger.error(f"清理语音文件失败 {user_dir}: {e}")
            logger.info(f"已处理 {voice_cleaned} 个用户的语音文件清理")

        logger.info("历史记录清理完成")

    # 添加定时任务
    job_queue = app.job_queue
    if job_queue:
        job_queue.run_daily(cleanup_job, time=time(hour=3, minute=0))
        logger.info("已设置每日凌晨 3 点自动清理过期历史记录")

    logger.info("Bot 启动中...")
    logger.info(f"用户数据目录: {users_data_dir}")
    logger.info(f"默认配额: {default_quota_gb}GB")
    logger.info(f"会话超时: {session_timeout // 60} 分钟")
    logger.info(f"允许新用户: {allow_new_users}")
    logger.info(f"管理员: {admin_users}")

    # Mini App API 配置
    api_enabled = config.get("mini_app_api_enabled", True)
    api_port = config.get("mini_app_api_port", 8000)
    api_dev_mode = config.get("mini_app_api_dev_mode", False)

    # 启动 Bot 和 API 服务器
    async with app:
        await app.start()
        await app.updater.start_polling(allowed_updates=["message", "callback_query"])

        # Start API server if enabled
        api_task = None
        if api_enabled:
            api_task = asyncio.create_task(
                run_api_server(
                    user_manager=user_manager,
                    session_manager=session_manager,
                    schedule_manager=schedule_manager,
                    bot_token=bot_token,
                    allow_new_users=allow_new_users,
                    host="0.0.0.0",
                    port=api_port,
                    dev_mode=api_dev_mode,
                    skill_manager=skill_manager,
                    api_config=api_config
                )
            )
            logger.info(f"Mini App API server starting on port {api_port}")

        # Keep running until interrupted
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            logger.info("Shutting down...")
        finally:
            if api_task:
                api_task.cancel()
                try:
                    await api_task
                except asyncio.CancelledError:
                    pass
            await app.updater.stop()
            await app.stop()


def main():
    """同步入口点"""
    asyncio.run(main_async())


if __name__ == "__main__":
    main()
