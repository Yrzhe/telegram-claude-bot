#!/usr/bin/env python3
"""Telegram 文件管理 Bot 入口"""

import json
import logging
from pathlib import Path
from datetime import time
from telegram.ext import Application

from bot import setup_handlers, UserManager, SessionManager
from bot.schedule import ScheduleManager
from bot.skill import SkillManager


def load_config(config_path: str = "config.json") -> dict:
    """加载配置文件"""
    config_file = Path(config_path)
    if not config_file.exists():
        raise FileNotFoundError(f"配置文件不存在: {config_path}")

    with open(config_file, 'r', encoding='utf-8') as f:
        return json.load(f)


def main():
    """主函数"""
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
    skill_manager = SkillManager(users_base_path=users_data_dir)

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
        skill_manager=skill_manager
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

            sub_system_prompt = f"""You are executing a scheduled task: {task_name}

RULES:
1. Complete the task independently
2. If you create report files, you MUST send them using send_telegram_file tool
3. NEVER show full system paths like /app/users/xxx - use relative paths only
4. You cannot send text messages to users - only files
5. Be efficient and complete the task without unnecessary steps

Task instructions:
"""

            try:
                response = await sub_agent.process_message(
                    prompt,
                    custom_system_prompt=sub_system_prompt
                )

                # Send completion message with result
                result_text = response.text or "Task completed"
                if len(result_text) > 3000:
                    result_text = result_text[:3000] + "... (truncated)"

                await app.bot.send_message(
                    chat_id=user_id,
                    text=f"✅ Scheduled task completed: {task_name}\n\n{result_text}"
                )

                # Send tracked files after task completion
                try:
                    new_files = file_tracker.get_new_files()
                    if new_files:
                        sent_count = await send_tracked_files(
                            files=new_files,
                            working_dir=user_data_path,
                            send_file_callback=send_file
                        )
                        if sent_count > 0:
                            logger.info(f"Scheduled task {task_id}: Sent {sent_count} new files to user {user_id}")
                except Exception as e:
                    logger.error(f"Failed to send tracked files for scheduled task: {e}")

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

    # 运行 Bot
    app.run_polling(allowed_updates=["message", "callback_query"])


if __name__ == "__main__":
    main()
