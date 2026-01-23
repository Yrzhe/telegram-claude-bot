"""Telegram Bot command handlers"""

import logging
import tempfile
import asyncio
import random
from io import BytesIO
from datetime import datetime
from pathlib import Path
from telegram import Update, ReactionTypeEmoji
from telegram.constants import ChatAction
from telegram.ext import (
    ContextTypes,
    CommandHandler,
    MessageHandler,
    filters,
    Application
)

from .agent import TelegramAgentClient, create_sub_agent
from .agent.message_handler import get_message_handler
from .agent.task_manager import TaskManager, SubAgentTask
from .agent.review import create_review_callback
from .agent.tools import clean_markdown_for_telegram
from .user import UserManager
from .session import SessionManager, ChatLogger
from .schedule import ScheduleManager
from .skill import SkillManager
from .custom_command import CustomCommandManager
from .i18n import t, get_tool_display_name

logger = logging.getLogger(__name__)

# Message length threshold, messages exceeding this will be sent as files
MAX_MESSAGE_LENGTH = 2000


# Responses that should be filtered out (Claude internal messages)
SKIP_RESPONSES = [
    "No response requested.",
    "No response requested",
    "no response requested.",
    "no response requested",
]


def should_skip_response(text: str | None) -> bool:
    """Check if a response should be skipped (not sent to user)."""
    if not text:
        return True
    text_stripped = text.strip()
    return text_stripped in SKIP_RESPONSES or text_stripped.lower() == "no response requested."


async def send_long_message(update: Update, text: str, caption: str | None = None):
    """
    Send message, if too long send as txt file

    Args:
        update: Telegram Update object
        text: Text to send
        caption: Caption when sending as file
    """
    # Skip internal Claude messages
    if should_skip_response(text):
        return

    # Clean markdown formatting for Telegram
    text = clean_markdown_for_telegram(text)

    if len(text) <= MAX_MESSAGE_LENGTH:
        await update.message.reply_text(text)
    else:
        file_bytes = BytesIO(text.encode('utf-8'))
        file_bytes.name = "response.txt"
        await update.message.reply_document(
            document=file_bytes,
            caption=caption or t("LONG_RESPONSE_CAPTION"),
            filename="response.txt"
        )


# ===== Typing Indicator =====

class TypingIndicator:
    """Context manager to show typing indicator while processing"""

    def __init__(self, bot, chat_id: int, interval: float = 4.0):
        self.bot = bot
        self.chat_id = chat_id
        self.interval = interval
        self._task: asyncio.Task | None = None
        self._stopped = False

    async def _send_typing_loop(self):
        """Continuously send typing action"""
        while not self._stopped:
            try:
                await self.bot.send_chat_action(
                    chat_id=self.chat_id,
                    action=ChatAction.TYPING
                )
            except Exception as e:
                logger.debug(f"Typing indicator failed: {e}")
            await asyncio.sleep(self.interval)

    async def start(self):
        """Start showing typing indicator"""
        self._stopped = False
        self._task = asyncio.create_task(self._send_typing_loop())

    async def stop(self):
        """Stop showing typing indicator"""
        self._stopped = True
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None


# ===== Message Reactions =====

# Available emoji reactions for Telegram
REACTION_EMOJIS = [
    "👍", "👎", "❤", "🔥", "🥰", "👏", "😁", "🤔",
    "🤯", "😱", "🤬", "😢", "🎉", "🤩", "🤮", "💩",
    "🙏", "👌", "🕊", "🤡", "🥱", "🥴", "😍", "🐳",
    "❤‍🔥", "🌚", "🌭", "💯", "🤣", "⚡", "🍌", "🏆",
    "💔", "🤨", "😐", "🍓", "🍾", "💋", "🖕", "😈",
    "😴", "😭", "🤓", "👻", "👨‍💻", "👀", "🎃", "🙈",
    "😇", "😨", "🤝", "✍", "🤗", "🫡", "🎅", "🎄",
    "☃", "💅", "🤪", "🗿", "🆒", "💘", "🙉", "🦄",
    "😘", "💊", "🙊", "😎", "👾", "🤷‍♂", "🤷", "🤷‍♀",
    "😡"
]

# Common positive reactions
POSITIVE_REACTIONS = ["👍", "❤", "🔥", "👏", "😁", "🎉", "🤩", "💯", "👌", "🤗"]
# Thinking/curious reactions
THINKING_REACTIONS = ["🤔", "👀", "🤓", "✍", "👨‍💻"]
# Fun/playful reactions
FUN_REACTIONS = ["😂", "🤣", "😎", "🦄", "🐳", "🎃", "👻", "🤪"]
# Supportive reactions
SUPPORTIVE_REACTIONS = ["🙏", "❤", "🤗", "😇", "💪"]


async def maybe_add_reaction(
    bot,
    chat_id: int,
    message_id: int,
    user_message: str,
    api_config: dict,
    probability: float = 0.3
) -> bool:
    """
    Maybe add a reaction to user's message using a lightweight LLM.

    Args:
        bot: Telegram bot instance
        chat_id: Chat ID
        message_id: Message ID to react to
        user_message: User's message text
        api_config: API configuration
        probability: Probability of reacting (0-1)

    Returns:
        True if reaction was added
    """
    # Random probability check
    if random.random() > probability:
        return False

    # Skip very short messages
    if len(user_message.strip()) < 5:
        return False

    try:
        emoji = await _get_reaction_emoji(user_message, api_config)
        if emoji:
            await bot.set_message_reaction(
                chat_id=chat_id,
                message_id=message_id,
                reaction=[ReactionTypeEmoji(emoji=emoji)]
            )
            logger.debug(f"Added reaction {emoji} to message {message_id}")
            return True
    except Exception as e:
        logger.debug(f"Failed to add reaction: {e}")

    return False


async def _get_reaction_emoji(message: str, api_config: dict) -> str | None:
    """
    Use a lightweight LLM to decide on a reaction emoji.

    Args:
        message: User's message
        api_config: API configuration

    Returns:
        Emoji string or None if no reaction needed
    """
    import anthropic

    api_key = api_config.get("api_key")
    base_url = api_config.get("base_url")

    if not api_key:
        # Fallback to random positive reaction
        return random.choice(POSITIVE_REACTIONS)

    try:
        client_args = {"api_key": api_key}
        if base_url:
            client_args["base_url"] = base_url

        client = anthropic.Anthropic(**client_args)

        # Use Haiku for speed and cost
        response = client.messages.create(
            model="claude-3-5-haiku-20241022",
            max_tokens=10,
            messages=[{
                "role": "user",
                "content": f"""Given this message, respond with ONLY a single emoji reaction that fits the mood/content.
If the message doesn't warrant a reaction, respond with "NONE".

Available emojis: 👍 ❤ 🔥 👏 😁 🎉 🤩 💯 👌 🤗 🤔 👀 🤓 😂 🤣 😎 🦄 🙏 😇 💪 ✍ 👨‍💻

Message: {message[:200]}

Response (emoji only or NONE):"""
            }]
        )

        result = response.content[0].text.strip()
        if result == "NONE" or len(result) > 4:
            return None

        # Validate emoji is in our list
        if result in REACTION_EMOJIS:
            return result

        # If LLM returned something unexpected, use a safe default
        return None

    except Exception as e:
        logger.debug(f"Reaction LLM failed: {e}")
        # On error, don't add reaction instead of random fallback
        return None


def setup_handlers(
    app: Application,
    user_manager: UserManager,
    session_manager: SessionManager,
    admin_users: list[int],
    allow_new_users: bool = True,
    api_config: dict | None = None,
    schedule_manager: ScheduleManager | None = None,
    skill_manager: SkillManager | None = None
):
    """
    Set up all command handlers

    Args:
        app: Telegram Application instance
        user_manager: User manager
        session_manager: Session manager
        admin_users: Admin user ID list
        schedule_manager: Schedule manager for scheduled tasks
        skill_manager: Skill manager for user skills
        allow_new_users: Whether to allow new users
        api_config: API config (api_key, base_url, model)
    """
    user_agents: dict[int, TelegramAgentClient] = {}
    task_managers: dict[int, TaskManager] = {}
    api_config = api_config or {}

    # 创建对话日志记录器
    chat_logger = ChatLogger(user_manager.base_path)

    # 初始化自定义命令管理器（使用第一个 admin 用户的数据目录）
    custom_command_manager: CustomCommandManager | None = None
    if admin_users:
        primary_admin_id = admin_users[0]
        admin_data_path = user_manager.get_user_data_path(primary_admin_id)
        custom_command_manager = CustomCommandManager(admin_data_path)
        logger.info(f"Custom command manager initialized with {len(custom_command_manager.get_all_commands())} commands")

    # 用于追踪 admin 待添加媒体的命令
    pending_media_commands: dict[int, str] = {}  # admin_user_id -> command_name

    def is_admin(user_id: int) -> bool:
        return user_id in admin_users or user_manager.is_admin(user_id)

    def can_access(user_id: int) -> bool:
        """检查用户是否有访问权限（不会自动创建用户）"""
        # 先检查用户是否存在
        if not user_manager.user_exists(user_id):
            if allow_new_users:
                # 允许新用户，稍后会创建
                return True
            else:
                # 不允许新用户
                return False
        # 用户存在，检查是否启用
        config = user_manager.get_user_config(user_id)
        return config.enabled

    async def handle_unauthorized_user(update, context):
        """处理未授权用户：通知管理员 + 发送推特联系提示"""
        user = update.effective_user
        user_id = user.id
        username = user.username or ""
        first_name = user.first_name or ""

        # 记录用户信息（但不启用）
        if not user_manager.user_exists(user_id):
            config = user_manager.create_user(user_id, username, first_name)
            config.enabled = False  # 明确设置为禁用
            user_manager._save_configs()

        # 通知所有管理员
        user_display = f"@{username}" if username else first_name or str(user_id)
        admin_message = (
            f"🆕 新用户尝试访问\n\n"
            f"ID: {user_id}\n"
            f"用户名: @{username}\n"
            f"名字: {first_name}\n\n"
            f"使用 /admin enable {user_id} 启用此用户"
        )

        for admin_id in admin_users:
            try:
                await context.bot.send_message(chat_id=admin_id, text=admin_message)
            except Exception as e:
                logger.warning(f"无法通知管理员 {admin_id}: {e}")

        # 给用户发送联系提示
        await update.message.reply_text(
            f"抱歉，您还没有使用权限。\n\n"
            f"请联系管理员获取访问权限：\n"
            f"🐦 Twitter: https://x.com/yrzhe_top\n\n"
            f"请告知您的用户 ID: {user_id}"
        )

    def get_task_manager(user_id: int, bot=None) -> TaskManager:
        """Get or create TaskManager for user"""
        if user_id not in task_managers:
            # Callback when Sub Agent completes - just log, don't send to user
            # Main agent should use get_task_result to retrieve and present results
            async def on_task_complete(task_id: str, description: str, result: str):
                """Log Sub Agent task completion (main agent will retrieve results)"""
                logger.info(f"Sub Agent task {task_id} completed for user {user_id}: {description[:50]}...")

            # Get user's working directory for task documents
            user_data_path = user_manager.get_user_data_path(user_id)
            task_managers[user_id] = TaskManager(
                user_id,
                on_task_complete=on_task_complete,
                working_directory=str(user_data_path)
            )
        return task_managers[user_id]

    def get_agent_for_user(user_id: int, bot) -> TelegramAgentClient:
        """Get or create Agent client for user"""
        user_data_path = user_manager.init_user(user_id)
        storage_info = user_manager.get_user_storage_info(user_id)
        env_vars = user_manager.get_user_env_vars(user_id)
        tm = get_task_manager(user_id, bot)

        def check_quota(additional_bytes: int) -> tuple[bool, str]:
            return user_manager.check_user_quota(user_id, additional_bytes)

        async def send_message(text: str):
            if len(text) > 4000:
                for i in range(0, len(text), 4000):
                    await bot.send_message(chat_id=user_id, text=text[i:i+4000])
            else:
                await bot.send_message(chat_id=user_id, text=text)

        async def send_file(file_path: str, caption: str | None) -> bool:
            from pathlib import Path

            # Build list of candidate paths to try
            candidates = []
            file_path_obj = Path(file_path)

            # 1. Try as provided (relative to user_data_path)
            candidates.append(user_data_path / file_path)

            # 2. If absolute path, try directly
            if file_path_obj.is_absolute():
                candidates.append(file_path_obj)

            # 3. Try just the filename in user_data_path root
            if file_path_obj.name != file_path:
                candidates.append(user_data_path / file_path_obj.name)

            # 4. Search common subdirectories for the filename
            common_subdirs = ['reports', 'analysis', 'documents', 'uploads', 'output']
            for subdir in common_subdirs:
                subdir_path = user_data_path / subdir
                if subdir_path.exists():
                    candidates.append(subdir_path / file_path_obj.name)
                    # Also try full relative path under subdir
                    if file_path_obj.name != file_path:
                        candidates.append(subdir_path / file_path)

            # Find first existing file
            full_path = None
            tried_paths = []
            for candidate in candidates:
                if candidate and candidate.exists() and candidate.is_file():
                    full_path = candidate
                    break
                if candidate:
                    tried_paths.append(str(candidate))

            if not full_path:
                logger.warning(
                    f"File not found for user {user_id}: '{file_path}'. "
                    f"Tried paths: {tried_paths[:5]}"  # Log first 5 paths
                )
                return False

            # Check file size (50MB limit for Telegram)
            if full_path.stat().st_size > 50 * 1024 * 1024:
                await bot.send_message(
                    chat_id=user_id,
                    text=t("FILE_TOO_LARGE")
                )
                return False

            try:
                await bot.send_document(
                    chat_id=user_id,
                    document=open(full_path, 'rb'),
                    caption=caption
                )
                logger.info(f"File sent to user {user_id}: {full_path}")
                return True
            except Exception as e:
                logger.error(f"Failed to send file to user {user_id}: {full_path}, error: {e}")
                return False

        # Create delegate callback for Sub Agent tasks
        async def delegate_callback(description: str, prompt: str) -> str | None:
            """Create a Sub Agent task"""
            agent_env_vars_copy = env_vars.copy()
            if api_config.get("api_key"):
                agent_env_vars_copy["ANTHROPIC_API_KEY"] = api_config["api_key"]
            if api_config.get("base_url"):
                agent_env_vars_copy["ANTHROPIC_BASE_URL"] = api_config["base_url"]

            async def executor(task: SubAgentTask) -> str:
                """Execute the Sub Agent task"""
                sub_agent = create_sub_agent(
                    user_id=user_id,
                    working_directory=str(user_data_path),
                    env_vars=agent_env_vars_copy,
                    model=api_config.get("model"),
                    mistral_api_key=api_config.get("mistral_api_key"),
                    send_file_callback=send_file
                )

                # Create system prompt for sub agent
                sub_system_prompt = f"""You are a Sub Agent working on a delegated task.
Task: {description}

RULES:
1. Work independently to complete this task
2. If you create report files, you MUST send them using send_telegram_file tool
3. NEVER show full system paths like /app/users/xxx - use relative paths only (e.g., analysis/report.md)
4. After completing, return a brief summary (the user will receive files separately)
5. You cannot send text messages to users - only files

FILE PATH RULES (CRITICAL):
- You can ONLY create/write files in these directories: reports/, analysis/, documents/, output/
- NEVER use /tmp, /var, or any system directory - they are blocked
- Always use relative paths like "reports/my_report.txt", NOT absolute paths
- Example: Write to "reports/tariff_monitor.md", then send with send_telegram_file("reports/tariff_monitor.md")

Working directory: (hidden for security)
"""
                response = await sub_agent.process_message(
                    prompt,
                    custom_system_prompt=sub_system_prompt
                )

                return response.text or f"Task completed: {description}"

            # Use a placeholder parent_message_id (current time)
            parent_id = str(datetime.now().timestamp())
            task = await tm.create_task(parent_id, description, executor, prompt=prompt)

            if task:
                return task.task_id
            return None

        # Create delegate callback for Sub Agent tasks with quality review
        async def delegate_review_callback(description: str, prompt: str, review_criteria: str) -> str | None:
            """Create a Sub Agent task with automatic quality review"""
            agent_env_vars_copy = env_vars.copy()
            if api_config.get("api_key"):
                agent_env_vars_copy["ANTHROPIC_API_KEY"] = api_config["api_key"]
            if api_config.get("base_url"):
                agent_env_vars_copy["ANTHROPIC_BASE_URL"] = api_config["base_url"]

            # Create review callback for quality evaluation
            review_cb = await create_review_callback(
                api_key=api_config.get("api_key", ""),
                base_url=api_config.get("base_url"),
                model=api_config.get("model", "claude-sonnet-4-20250514")
            )

            async def executor(task: SubAgentTask) -> str:
                """Execute the Sub Agent task"""
                sub_agent = create_sub_agent(
                    user_id=user_id,
                    working_directory=str(user_data_path),
                    env_vars=agent_env_vars_copy,
                    model=api_config.get("model"),
                    mistral_api_key=api_config.get("mistral_api_key"),
                    send_file_callback=send_file
                )

                # Build prompt with retry context if this is a retry
                current_prompt = prompt
                if task.retry_count > 0 and task.retry_history:
                    last_feedback = task.retry_history[-1].get("feedback", "")
                    current_prompt = f"""{prompt}

=== IMPORTANT: This is retry #{task.retry_count + 1} ===
Previous attempt was rejected with the following feedback:
{last_feedback}

Please address the issues mentioned above and improve your response."""

                # Create system prompt for sub agent
                sub_system_prompt = f"""You are a Sub Agent working on a delegated task.
Task: {description}

QUALITY CRITERIA (your output will be reviewed against these):
{review_criteria}

RULES:
1. Work independently to complete this task
2. If you create report files, you MUST send them using send_telegram_file tool
3. NEVER show full system paths like /app/users/xxx - use relative paths only (e.g., analysis/report.md)
4. After completing, return a comprehensive result that meets the quality criteria
5. You cannot send text messages to users - only files

FILE PATH RULES (CRITICAL):
- You can ONLY create/write files in these directories: reports/, analysis/, documents/, output/
- NEVER use /tmp, /var, or any system directory - they are blocked
- Always use relative paths like "reports/my_report.txt", NOT absolute paths
- Example: Write to "reports/tariff_monitor.md", then send with send_telegram_file("reports/tariff_monitor.md")

Working directory: (hidden for security)
"""
                response = await sub_agent.process_message(
                    current_prompt,
                    custom_system_prompt=sub_system_prompt
                )

                return response.text or f"Task completed: {description}"

            # Progress callback to send updates to user
            async def send_progress(message: str):
                """Send progress updates to user"""
                try:
                    await send_message(message)
                except Exception as e:
                    logger.error(f"Failed to send progress message: {e}")

            # Use a placeholder parent_message_id (current time)
            parent_id = str(datetime.now().timestamp())
            task = await tm.create_review_task(
                parent_message_id=parent_id,
                description=description,
                executor=executor,
                review_callback=review_cb,
                send_progress_callback=send_progress,
                prompt=prompt,
                review_criteria=review_criteria
            )

            if task:
                return task.task_id
            return None

        agent_env_vars = env_vars.copy()
        if api_config.get("api_key"):
            agent_env_vars["ANTHROPIC_API_KEY"] = api_config["api_key"]
        if api_config.get("base_url"):
            agent_env_vars["ANTHROPIC_BASE_URL"] = api_config["base_url"]

        # Get user's custom skills
        custom_skills_content = ""
        if skill_manager:
            custom_skills_content = skill_manager.get_skills_for_agent(user_id)

        # Get user display name (prefer username, fallback to first_name)
        user_config = user_manager.get_user_config(user_id)
        user_display_name = user_config.username or user_config.first_name or ""

        # Get context summary (from previous /compact)
        context_summary = user_manager.get_context_summary(user_id)

        user_agents[user_id] = TelegramAgentClient(
            user_id=user_id,
            working_directory=str(user_data_path),
            send_message_callback=send_message,
            send_file_callback=send_file,
            check_quota_callback=check_quota,
            delegate_callback=delegate_callback,
            delegate_review_callback=delegate_review_callback,
            env_vars=agent_env_vars,
            storage_info=storage_info,
            model=api_config.get("model"),
            mistral_api_key=api_config.get("mistral_api_key"),
            custom_skills_content=custom_skills_content,
            schedule_manager=schedule_manager,
            task_manager=tm,
            user_display_name=user_display_name,
            custom_command_manager=custom_command_manager,
            admin_user_ids=admin_users,
            context_summary=context_summary
        )
        return user_agents[user_id]

    async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id

        if not can_access(user_id):
            await handle_unauthorized_user(update, context)
            return

        # 更新用户信息（用户名可能会变化）
        user = update.effective_user
        user_manager.update_user_info(user_id, user.username or "", user.first_name or "")

        user_manager.init_user(user_id)
        storage_info = user_manager.get_user_storage_info(user_id)
        session_info = session_manager.get_session_info(user_id)

        session_text = ""
        if session_info:
            if session_info.get('no_expiry'):
                session_text = "\n" + t("SESSION_INFO_PERSISTENT",
                    message_count=session_info['message_count']
                )
            else:
                session_text = "\n" + t("SESSION_INFO",
                    message_count=session_info['message_count'],
                    remaining_minutes=session_info['remaining_minutes']
                )

        # 构建自定义命令列表
        custom_commands_text = ""
        if custom_command_manager:
            user_commands = custom_command_manager.get_commands_for_user(user_id)
            if user_commands:
                custom_commands_text = "\n\n🎯 专属命令:\n"
                for cmd in user_commands:
                    custom_commands_text += f"/{cmd.name} - {cmd.description}\n"

        # Admin 命令提示
        admin_commands_text = ""
        if is_admin(user_id):
            admin_commands_text = "\n\n👑 管理员命令:\n/admin - 用户管理、自定义命令管理"

        help_text = f"""
{t("WELCOME_TITLE")}

{t("STORAGE_LABEL")}
{t("USED_LABEL")}: {storage_info['used_formatted']} / {storage_info['quota_formatted']} ({storage_info['percentage']}%){session_text}

{t("AI_MODE_DESC")}

{t("COMMAND_LIST_TITLE")}
{t("CMD_LS")}
{t("CMD_STORAGE")}
{t("CMD_STATUS")}
{t("CMD_SESSION")}
{t("CMD_NEW")}
{t("CMD_COMPACT")}
{t("CMD_ENV")}
{t("CMD_PACKAGES")}
{t("CMD_SCHEDULE")}
{t("CMD_SKILL")}
{t("CMD_HELP")}{custom_commands_text}{admin_commands_text}

{t("EXAMPLES_TITLE")}
{t("EXAMPLE_CREATE_FILE")}
{t("EXAMPLE_LIST_FILES")}
        """
        await update.message.reply_text(help_text)

    async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
        await start(update, context)

    async def session_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """View session status"""
        user_id = update.effective_user.id

        if not can_access(user_id):
            await handle_unauthorized_user(update, context)
            return

        session_info = session_manager.get_session_info(user_id)

        if not session_info:
            await update.message.reply_text(t("NO_ACTIVE_SESSION"))
            return

        if session_info.get('no_expiry'):
            remaining_text = t("NO_EXPIRY")
        else:
            remaining_text = f"{session_info['remaining_minutes']} {t('MINUTES')}"

        text = f"""
{t("SESSION_STATUS_TITLE")}

{t("SESSION_ID_LABEL")}: {session_info['session_id']}
{t("MESSAGE_COUNT_LABEL")}: {session_info['message_count']}
{t("IDLE_TIME_LABEL")}: {session_info['elapsed_seconds']} {t("SECONDS")}
{t("REMAINING_TIME_LABEL")}: {remaining_text}

{t("NEW_SESSION_HINT")}
        """
        await update.message.reply_text(text)

    async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """View session status with usage statistics"""
        user_id = update.effective_user.id

        if not can_access(user_id):
            await handle_unauthorized_user(update, context)
            return

        session_info = session_manager.get_session_info(user_id)

        if not session_info:
            await update.message.reply_text(t("STATUS_NO_SESSION"))
            return

        # Format time remaining
        if session_info.get('no_expiry'):
            remaining_text = t("NO_EXPIRY")
        else:
            remaining_text = f"{session_info['remaining_minutes']} {t('MINUTES')}"

        # Format cost
        cost_usd = session_info.get('total_cost_usd', 0)
        if cost_usd >= 0.01:
            cost_text = f"${cost_usd:.2f}"
        elif cost_usd > 0:
            cost_text = f"${cost_usd:.4f}"
        else:
            cost_text = "$0.00"

        # Format tokens (with K notation for large numbers)
        input_tokens = session_info.get('total_input_tokens', 0)
        output_tokens = session_info.get('total_output_tokens', 0)
        total_tokens = input_tokens + output_tokens

        def format_tokens(n: int) -> str:
            if n >= 1000000:
                return f"{n/1000000:.1f}M"
            elif n >= 1000:
                return f"{n/1000:.1f}K"
            return str(n)

        # Get model name from api_config
        model_name = api_config.get('model', 'unknown') if api_config else 'unknown'
        # Simplify model name for display
        if '/' in model_name:
            model_name = model_name.split('/')[-1]
        if model_name.startswith('claude-'):
            model_name = model_name[7:]  # Remove 'claude-' prefix

        text = f"""📊 {t("STATUS_TITLE")}

🔗 {t("STATUS_SESSION_LABEL")}: {session_info['session_id']}
💬 {t("STATUS_MESSAGES_LABEL")}: {session_info['message_count']}
🔄 {t("STATUS_TURNS_LABEL")}: {session_info.get('total_turns', 0)}

📈 {t("STATUS_TOKENS_LABEL")}:
   {t("STATUS_INPUT_LABEL")}: {format_tokens(input_tokens)}
   {t("STATUS_OUTPUT_LABEL")}: {format_tokens(output_tokens)}
   {t("STATUS_TOTAL_LABEL")}: {format_tokens(total_tokens)}

💰 {t("STATUS_COST_LABEL")}: {cost_text}

⏱️ {t("STATUS_TIME_LABEL")}:
   {t("STATUS_ACTIVE_LABEL")}: {session_info['elapsed_seconds']}s
   {t("STATUS_REMAINING_LABEL")}: {remaining_text}

🤖 {t("STATUS_MODEL_LABEL")}: {model_name}
"""
        await update.message.reply_text(text)

    async def new_session_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Start new session with conversation summary"""
        user_id = update.effective_user.id

        if not can_access(user_id):
            await handle_unauthorized_user(update, context)
            return

        # 获取当前会话信息
        session = session_manager.get_session(user_id)
        session_id = session.session_id if session else None

        # 检查是否有对话日志需要总结
        chat_log = chat_logger.get_current_session_log(user_id, session_id)

        if chat_log and len(chat_log) > 100:
            # 有对话内容，生成总结并归档
            thinking_msg = await update.message.reply_text("📝 正在总结对话记录...")

            try:
                # 生成对话总结
                summary = await _generate_chat_summary(
                    user_id, chat_log, api_config, user_manager
                )

                # 归档日志（保存总结 + 原始记录）
                chat_logger.archive_session_log(user_id, session_id, summary)

                await thinking_msg.edit_text(
                    f"✅ 会话已结束\n\n📋 对话总结已保存\n\n{summary[:500]}{'...' if len(summary) > 500 else ''}"
                )
            except Exception as e:
                logger.error(f"生成对话总结失败: {e}")
                # 即使总结失败，也归档原始日志
                chat_logger.archive_session_log(
                    user_id, session_id,
                    f"[自动总结失败]\n\n消息数: {session.message_count if session else 'N/A'}"
                )
                await thinking_msg.edit_text("✅ 会话已结束（总结生成失败，已保存原始记录）")
        else:
            # 没有对话内容或内容很少
            if session_id:
                chat_logger.archive_session_log(
                    user_id, session_id,
                    f"[短对话，无需总结]\n\n消息数: {session.message_count if session else 0}"
                )

        # 清除会话
        had_session = session_manager.clear_session(user_id)

        if not chat_log or len(chat_log) <= 100:
            if had_session:
                await update.message.reply_text(t("SESSION_CLEARED"))
            else:
                await update.message.reply_text(t("NO_SESSION_TO_CLEAR"))

    async def compact_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Compact conversation context - generate summary and start fresh session"""
        user_id = update.effective_user.id

        if not can_access(user_id):
            await handle_unauthorized_user(update, context)
            return

        # Check if there's an active session
        session_info = session_manager.get_session_info(user_id)
        if not session_info:
            await update.message.reply_text(t("COMPACT_NO_SESSION"))
            return

        session = session_manager.get_session(user_id)
        if not session or not session.session_id:
            await update.message.reply_text(t("COMPACT_NO_SESSION"))
            return

        # Show processing message
        thinking_msg = await update.message.reply_text(t("COMPACT_PROCESSING"))

        try:
            # Get chat log for summary generation
            chat_log = chat_logger.get_current_session_log(user_id, session.session_id)

            # Generate summary
            summary = ""
            if chat_log and len(chat_log) > 50:
                summary = await _generate_context_summary(
                    user_id, chat_log, api_config, user_manager, session_info
                )
            else:
                # No substantial conversation, create minimal summary
                summary = f"Previous session had {session_info['message_count']} messages with minimal content."

            # Save context summary for next session
            user_manager.save_context_summary(user_id, summary)

            # Archive current chat log
            chat_logger.archive_session_log(user_id, session.session_id, summary)

            # Get stats before compacting
            message_count = session_info['message_count']
            total_tokens = session_info['total_tokens']
            cost = session_info['total_cost_usd']

            # Compact the session (clear session_id but keep stats)
            session_manager.compact_session(user_id)

            # Clear cached agent so it will be recreated with context summary
            if user_id in user_agents:
                del user_agents[user_id]

            await thinking_msg.edit_text(t("COMPACT_SUCCESS",
                message_count=message_count,
                total_tokens=total_tokens,
                cost=cost
            ))

        except Exception as e:
            logger.error(f"Failed to compact session for user {user_id}: {e}")
            await thinking_msg.edit_text(t("COMPACT_FAILED", error=str(e)))

    async def _generate_context_summary(
        user_id: int,
        chat_log: str,
        api_config: dict,
        user_manager: UserManager,
        session_info: dict
    ) -> str:
        """Generate comprehensive context summary for session continuation"""
        import asyncio
        import anthropic

        # Limit chat log length
        max_log_chars = 20000
        if len(chat_log) > max_log_chars:
            chat_log = chat_log[:max_log_chars] + "\n\n... [对话内容已截断]"

        api_key = api_config.get("api_key")
        base_url = api_config.get("base_url")

        if not api_key:
            return f"""Session Statistics:
- Messages: {session_info.get('message_count', 0)}
- Tokens used: {session_info.get('total_tokens', 0)}
- Cost: ${session_info.get('total_cost_usd', 0):.4f}

[Unable to generate detailed summary - no API key]"""

        def _call_api():
            client_args = {"api_key": api_key}
            if base_url:
                client_args["base_url"] = base_url

            client = anthropic.Anthropic(**client_args)

            response = client.messages.create(
                model=api_config.get("model", "claude-sonnet-4-20250514"),
                max_tokens=1000,
                messages=[{
                    "role": "user",
                    "content": f"""Please create a comprehensive summary of this conversation that will help continue the conversation seamlessly in a new session.

Include:
1. Main topics discussed
2. Key decisions or conclusions reached
3. Important user preferences or requirements mentioned
4. Any pending tasks or follow-ups
5. User's communication style/language preference

Format the summary in a way that's easy for an AI assistant to understand and use as context.

Conversation:
{chat_log}

Summary:"""
                }]
            )

            return response.content[0].text

        try:
            loop = asyncio.get_event_loop()
            summary = await loop.run_in_executor(None, _call_api)

            stats = f"""
---
Session Statistics:
- Messages: {session_info.get('message_count', 0)}
- Tokens: {session_info.get('total_tokens', 0)}
- Cost: ${session_info.get('total_cost_usd', 0):.4f}
- Compact #: {session_info.get('compact_count', 0) + 1}
---
"""
            return stats + summary

        except Exception as e:
            logger.error(f"Claude API summary generation failed: {e}")
            return f"""Session Statistics:
- Messages: {session_info.get('message_count', 0)}
- Tokens: {session_info.get('total_tokens', 0)}
- Cost: ${session_info.get('total_cost_usd', 0):.4f}

[API summary failed: {str(e)[:100]}]"""

    async def _auto_compact_session(user_id: int, update: Update):
        """Auto-compact session when token threshold is reached"""
        try:
            session_info = session_manager.get_session_info(user_id)
            if not session_info:
                return

            session = session_manager.get_session(user_id)
            if not session or not session.session_id:
                return

            total_tokens = session_info.get('total_tokens', 0)
            logger.info(f"Auto-compacting session for user {user_id} (tokens: {total_tokens})")

            # Notify user
            await update.message.reply_text(t("COMPACT_AUTO_TRIGGERED", tokens=total_tokens))

            # Get chat log
            chat_log = chat_logger.get_current_session_log(user_id, session.session_id)

            # Generate summary
            if chat_log and len(chat_log) > 50:
                summary = await _generate_context_summary(
                    user_id, chat_log, api_config, user_manager, session_info
                )
            else:
                summary = f"Previous session had {session_info['message_count']} messages."

            # Save context summary
            user_manager.save_context_summary(user_id, summary)

            # Archive chat log
            chat_logger.archive_session_log(user_id, session.session_id, summary)

            # Compact session
            session_manager.compact_session(user_id)

            # Clear cached agent
            if user_id in user_agents:
                del user_agents[user_id]

            logger.info(f"Auto-compact completed for user {user_id}")

        except Exception as e:
            logger.error(f"Auto-compact failed for user {user_id}: {e}")

    async def _generate_chat_summary(
        user_id: int,
        chat_log: str,
        api_config: dict,
        user_manager: UserManager
    ) -> str:
        """使用 Claude API 生成对话总结"""
        import asyncio
        import anthropic

        # 限制对话长度，避免 token 过多
        max_log_chars = 15000
        if len(chat_log) > max_log_chars:
            chat_log = chat_log[:max_log_chars] + "\n\n... [对话内容已截断]"

        api_key = api_config.get("api_key")
        base_url = api_config.get("base_url")

        if not api_key:
            # 没有 API key，生成简单统计
            lines = chat_log.split('\n')
            user_msgs = len([l for l in lines if l.startswith('👤')])
            agent_msgs = len([l for l in lines if l.startswith('🤖')])
            return f"对话统计:\n- 用户消息: {user_msgs} 条\n- Agent 回复: {agent_msgs} 条"

        def _call_api():
            """同步调用 API（在线程池中执行）"""
            client_args = {"api_key": api_key}
            if base_url:
                client_args["base_url"] = base_url

            client = anthropic.Anthropic(**client_args)

            response = client.messages.create(
                model=api_config.get("model", "claude-sonnet-4-20250514"),
                max_tokens=500,
                messages=[{
                    "role": "user",
                    "content": f"""请用中文简洁总结以下对话的主要内容和关键点（不超过 200 字）：

{chat_log}

总结格式：
- 主要话题：...
- 关键内容：...
- 用户需求：..."""
                }]
            )

            return response.content[0].text

        try:
            # 在线程池中执行同步 API 调用
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(None, _call_api)
        except Exception as e:
            logger.error(f"Claude API 总结失败: {e}")
            # 返回简单统计
            lines = chat_log.split('\n')
            user_msgs = len([l for l in lines if l.startswith('👤')])
            agent_msgs = len([l for l in lines if l.startswith('🤖')])
            return f"[API 总结失败]\n\n对话统计:\n- 用户消息: {user_msgs} 条\n- Agent 回复: {agent_msgs} 条"

    async def storage_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id

        if not can_access(user_id):
            await handle_unauthorized_user(update, context)
            return

        storage_info = user_manager.get_user_storage_info(user_id)

        percentage = storage_info['percentage']
        bar_length = 20
        filled = int(bar_length * percentage / 100)
        bar = '█' * filled + '░' * (bar_length - filled)

        text = f"""
{t("STORAGE_TITLE")}

{bar} {percentage}%

{t("USED_LABEL")}: {storage_info['used_formatted']}
{t("QUOTA_LABEL")}: {storage_info['quota_formatted']}
{t("AVAILABLE_LABEL")}: {storage_info['available_formatted']}
        """
        await update.message.reply_text(text)

    async def ls(update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id

        if not can_access(user_id):
            await handle_unauthorized_user(update, context)
            return

        user_data_path = user_manager.get_user_data_path(user_id)
        user_data_path.mkdir(parents=True, exist_ok=True)

        rel_path = " ".join(context.args) if context.args else ""
        target_path = user_data_path / rel_path

        if not target_path.exists():
            await update.message.reply_text(t("PATH_NOT_EXIST", path=rel_path))
            return

        # If it's a file, send it directly
        if target_path.is_file():
            try:
                await update.message.reply_document(
                    document=open(target_path, 'rb'),
                    filename=target_path.name,
                    caption=f"📄 {rel_path}"
                )
            except Exception as e:
                logger.error(f"Failed to send file {rel_path}: {e}")
                await update.message.reply_text(t("ERR_SEND_FILE_FAILED", error=str(e)))
            return

        if not target_path.is_dir():
            await update.message.reply_text(t("NOT_A_DIRECTORY", path=rel_path))
            return

        try:
            target_path.resolve().relative_to(user_data_path.resolve())
        except ValueError:
            await update.message.reply_text(t("ACCESS_DENIED"))
            return

        items = sorted(target_path.iterdir(), key=lambda x: (not x.is_dir(), x.name))

        display_path = f"/{rel_path}" if rel_path else "/"
        if not items:
            await update.message.reply_text(f"{t('DIRECTORY_LABEL', path=display_path)}\n\n{t('EMPTY_DIRECTORY')}")
            return

        # Count folders and files
        folder_count = sum(1 for item in items if item.is_dir())
        file_count = len(items) - folder_count

        response = f"{t('DIRECTORY_LABEL', path=display_path)}\n"
        response += f"{t('ITEM_COUNT', folders=folder_count, files=file_count)}\n\n"

        for item in items:
            if item.is_dir():
                # Count items inside folder
                try:
                    inner_items = list(item.iterdir())
                    inner_count = len(inner_items)
                    response += f"📁 {item.name}/ ({inner_count} items)\n"
                except PermissionError:
                    response += f"📁 {item.name}/\n"
            else:
                size = item.stat().st_size
                size_str = user_manager.storage.format_size(size)
                response += f"📄 {item.name} ({size_str})\n"

        # Add usage hint
        if rel_path:
            response += f"\n\n💡 /ls {rel_path}/<folder> - enter subfolder"
            response += f"\n🗑️ /del {rel_path}/<name> - delete"
        else:
            response += "\n\n💡 /ls <folder> - enter folder"
            response += "\n🗑️ /del <name> - delete"

        if len(response) > 4000:
            for i in range(0, len(response), 4000):
                await update.message.reply_text(response[i:i+4000])
        else:
            await update.message.reply_text(response)

    # Track pending folder deletions for confirmation
    pending_folder_deletions: dict[int, str] = {}

    async def del_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Delete file or folder"""
        user_id = update.effective_user.id

        if not can_access(user_id):
            await handle_unauthorized_user(update, context)
            return

        args = context.args or []
        if not args:
            await update.message.reply_text(t("DEL_USAGE"))
            return

        user_data_path = user_manager.get_user_data_path(user_id)

        # Check if this is a confirmation
        if args[0].lower() == "confirm" and user_id in pending_folder_deletions:
            target_rel_path = pending_folder_deletions.pop(user_id)
            target_path = user_data_path / target_rel_path

            if target_path.exists() and target_path.is_dir():
                try:
                    import shutil
                    shutil.rmtree(target_path)
                    await update.message.reply_text(t("DEL_FOLDER_SUCCESS", path=target_rel_path))
                except Exception as e:
                    await update.message.reply_text(t("DEL_FAILED", error=str(e)))
            else:
                await update.message.reply_text(t("PATH_NOT_EXIST", path=target_rel_path))
            return

        # Check if cancelling
        if args[0].lower() == "cancel" and user_id in pending_folder_deletions:
            del pending_folder_deletions[user_id]
            await update.message.reply_text(t("DEL_CANCELLED"))
            return

        rel_path = " ".join(args)
        target_path = user_data_path / rel_path

        # Security check
        try:
            target_path.resolve().relative_to(user_data_path.resolve())
        except ValueError:
            await update.message.reply_text(t("ACCESS_DENIED"))
            return

        if not target_path.exists():
            await update.message.reply_text(t("PATH_NOT_EXIST", path=rel_path))
            return

        if target_path.is_dir():
            # Folder deletion requires confirmation
            item_count = len(list(target_path.rglob("*")))
            pending_folder_deletions[user_id] = rel_path
            await update.message.reply_text(t("DEL_FOLDER_CONFIRM", path=rel_path, count=item_count))
        else:
            # File deletion - direct with warning
            try:
                file_size = target_path.stat().st_size
                size_str = user_manager.storage.format_size(file_size)
                target_path.unlink()
                await update.message.reply_text(t("DEL_FILE_SUCCESS", path=rel_path, size=size_str))
            except Exception as e:
                await update.message.reply_text(t("DEL_FAILED", error=str(e)))

    async def env_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id

        if not can_access(user_id):
            await handle_unauthorized_user(update, context)
            return

        args = context.args or []

        if not args:
            env_vars = user_manager.get_user_env_vars(user_id)
            if not env_vars:
                await update.message.reply_text(f"{t('NO_ENV_VARS')}\n\n{t('ENV_USAGE')}")
                return

            text = f"{t('ENV_TITLE')}\n\n"
            for key, value in env_vars.items():
                display_value = value[:4] + "****" if len(value) > 8 else "****"
                text += f"{key} = {display_value}\n"
            text += f"\n{t('ENV_USAGE')}"
            await update.message.reply_text(text)

        elif args[0] == 'set' and len(args) >= 3:
            key = args[1]
            value = ' '.join(args[2:])
            if user_manager.set_user_env_var(user_id, key, value):
                await update.message.reply_text(t("ENV_SET_SUCCESS", key=key))
            else:
                await update.message.reply_text(t("ENV_SET_FAILED"))

        elif args[0] == 'del' and len(args) >= 2:
            key = args[1]
            if user_manager.delete_user_env_var(user_id, key):
                await update.message.reply_text(t("ENV_DEL_SUCCESS", key=key))
            else:
                await update.message.reply_text(t("ENV_DEL_FAILED"))

        else:
            await update.message.reply_text(t("ENV_USAGE"))

    async def packages_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id

        if not can_access(user_id):
            await handle_unauthorized_user(update, context)
            return

        args = context.args or []

        if not args:
            await update.message.reply_text(
                f"{t('PACKAGES_TITLE')}\n\n"
                f"{t('PACKAGES_LIST')}\n"
                f"{t('PACKAGES_INSTALL')}\n"
                f"{t('PACKAGES_INIT')}"
            )

        elif args[0] == 'init':
            await update.message.reply_text(t("CREATING_VENV"))
            success = await user_manager.create_user_venv(user_id)
            if success:
                await update.message.reply_text(t("VENV_SUCCESS"))
            else:
                await update.message.reply_text(t("VENV_FAILED"))

        elif args[0] == 'list':
            success, output = await user_manager.list_user_packages(user_id)
            if success:
                if output.strip():
                    await update.message.reply_text(f"{t('INSTALLED_PACKAGES')}\n\n{output}")
                else:
                    await update.message.reply_text(t("NO_PACKAGES"))
            else:
                await update.message.reply_text(t("GET_PACKAGES_FAILED", error=output))

        elif args[0] == 'install' and len(args) >= 2:
            package = args[1]
            await update.message.reply_text(t("INSTALLING_PACKAGE", package=package))
            success, output = await user_manager.install_user_package(user_id, package)
            if success:
                await update.message.reply_text(t("INSTALL_SUCCESS", package=package))
            else:
                await update.message.reply_text(t("INSTALL_FAILED", error=output))

        else:
            await update.message.reply_text(t("PACKAGES_USAGE"))

    # Track users waiting to input prompt for new schedule
    pending_schedule_prompts: dict[int, str] = {}  # user_id -> task_id

    async def schedule_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /schedule command for managing scheduled tasks"""
        user_id = update.effective_user.id

        if not can_access(user_id):
            await handle_unauthorized_user(update, context)
            return

        if not schedule_manager:
            await update.message.reply_text("Schedule feature not available")
            return

        args = context.args or []

        if not args:
            # Show help
            await update.message.reply_text(t("SCHEDULE_HELP"))
            return

        subcommand = args[0].lower()

        if subcommand == "list":
            # List all tasks
            tasks = schedule_manager.get_tasks(user_id)
            timezone = schedule_manager.get_user_timezone(user_id)

            if not tasks:
                await update.message.reply_text(
                    f"{t('SCHEDULE_TIMEZONE_LABEL')}: {timezone}\n\n{t('SCHEDULE_LIST_EMPTY')}"
                )
                return

            lines = [f"{t('SCHEDULE_LIST_TITLE')}", f"{t('SCHEDULE_TIMEZONE_LABEL')}: {timezone}\n"]
            for task in tasks:
                # Determine status emoji
                if task.max_runs and task.run_count >= task.max_runs:
                    status = "⏸️"  # Completed (reached max)
                elif task.enabled:
                    status = "🟢"
                else:
                    status = "🔴"

                schedule_str = schedule_manager.format_schedule_type(task)
                run_count_str = schedule_manager.format_run_count(task)
                last_run = task.last_run[:16].replace("T", " ") if task.last_run else t("SCHEDULE_NEVER_RUN")

                # Status text
                if task.max_runs and task.run_count >= task.max_runs:
                    status_text = "已完成"
                elif task.enabled:
                    status_text = "启用"
                else:
                    status_text = "禁用"

                lines.append(
                    f"{status} {task.name}\n"
                    f"   ID: {task.task_id}\n"
                    f"   周期: {schedule_str}\n"
                    f"   执行: {run_count_str} 次\n"
                    f"   状态: {status_text}\n"
                    f"   上次: {last_run}"
                )

            await update.message.reply_text("\n\n".join(lines))

        elif subcommand == "add":
            # New format: /schedule add <id> <type> <type_params...> [--max N] <name...>
            # Examples:
            #   /schedule add task1 daily 09:00 任务名
            #   /schedule add task2 weekly 09:00 mon,wed,fri 任务名
            #   /schedule add task3 monthly 10:00 15 任务名
            #   /schedule add task4 interval 30m 任务名
            #   /schedule add task5 once 2025-01-20 14:00 任务名
            #   /schedule add task6 daily 09:00 --max 5 任务名
            # Legacy format (still supported):
            #   /schedule add <id> <HH:MM> <name...>

            if len(args) < 4:
                await update.message.reply_text(t("SCHEDULE_ADD_USAGE_NEW"))
                return

            task_id = args[1]

            # Validate task_id
            if not task_id.replace("_", "").isalnum():
                await update.message.reply_text(t("SCHEDULE_ADD_INVALID_ID"))
                return
            if len(task_id) > 32:
                await update.message.reply_text(t("SCHEDULE_ADD_ID_TOO_LONG"))
                return
            if schedule_manager.get_task(user_id, task_id):
                await update.message.reply_text(t("SCHEDULE_ADD_EXISTS", task_id=task_id))
                return

            # Check for --max and --start options
            max_runs = None
            start_time = None
            remaining_args = list(args[2:])

            # Parse --max
            i = 0
            while i < len(remaining_args):
                if remaining_args[i] == "--max" and i + 1 < len(remaining_args):
                    try:
                        max_runs = int(remaining_args[i + 1])
                        if max_runs <= 0:
                            raise ValueError()
                        remaining_args = remaining_args[:i] + remaining_args[i+2:]
                    except ValueError:
                        await update.message.reply_text("--max 后需要跟一个正整数")
                        return
                elif remaining_args[i] == "--start" and i + 1 < len(remaining_args):
                    start_time = remaining_args[i + 1]
                    remaining_args = remaining_args[:i] + remaining_args[i+2:]
                else:
                    i += 1

            # Detect schedule type
            schedule_type = remaining_args[0].lower() if remaining_args else ""

            from .schedule import (
                SCHEDULE_TYPE_DAILY, SCHEDULE_TYPE_WEEKLY, SCHEDULE_TYPE_MONTHLY,
                SCHEDULE_TYPE_INTERVAL, SCHEDULE_TYPE_ONCE, VALID_SCHEDULE_TYPES
            )

            # Parse based on schedule type
            hour, minute = 0, 0
            weekdays = None
            month_day = None
            interval_minutes = None
            run_date = None

            if schedule_type in VALID_SCHEDULE_TYPES:
                # New format with explicit type
                if schedule_type == SCHEDULE_TYPE_DAILY:
                    # daily HH:MM name...
                    if len(remaining_args) < 3:
                        await update.message.reply_text("格式: /schedule add <id> daily HH:MM 名称")
                        return
                    valid, hour, minute, err = schedule_manager.validate_time(remaining_args[1])
                    if not valid:
                        await update.message.reply_text(err)
                        return
                    name = " ".join(remaining_args[2:])

                elif schedule_type == SCHEDULE_TYPE_WEEKLY:
                    # weekly HH:MM mon,wed,fri name...
                    if len(remaining_args) < 4:
                        await update.message.reply_text("格式: /schedule add <id> weekly HH:MM mon,wed,fri 名称")
                        return
                    valid, hour, minute, err = schedule_manager.validate_time(remaining_args[1])
                    if not valid:
                        await update.message.reply_text(err)
                        return
                    valid, weekdays, err = schedule_manager.parse_weekdays(remaining_args[2])
                    if not valid:
                        await update.message.reply_text(err)
                        return
                    name = " ".join(remaining_args[3:])

                elif schedule_type == SCHEDULE_TYPE_MONTHLY:
                    # monthly HH:MM day name...
                    if len(remaining_args) < 4:
                        await update.message.reply_text("格式: /schedule add <id> monthly HH:MM 日期(1-31) 名称")
                        return
                    valid, hour, minute, err = schedule_manager.validate_time(remaining_args[1])
                    if not valid:
                        await update.message.reply_text(err)
                        return
                    try:
                        month_day = int(remaining_args[2])
                        if not (1 <= month_day <= 31):
                            raise ValueError()
                    except ValueError:
                        await update.message.reply_text("日期必须是 1-31 之间的数字")
                        return
                    name = " ".join(remaining_args[3:])

                elif schedule_type == SCHEDULE_TYPE_INTERVAL:
                    # interval 30m name...
                    if len(remaining_args) < 3:
                        await update.message.reply_text("格式: /schedule add <id> interval 30m/2h/1d 名称")
                        return
                    valid, interval_minutes, err = schedule_manager.parse_interval(remaining_args[1])
                    if not valid:
                        await update.message.reply_text(err)
                        return
                    name = " ".join(remaining_args[2:])
                    # For interval tasks, hour/minute not used

                elif schedule_type == SCHEDULE_TYPE_ONCE:
                    # once YYYY-MM-DD HH:MM name...
                    if len(remaining_args) < 4:
                        await update.message.reply_text("格式: /schedule add <id> once YYYY-MM-DD HH:MM 名称")
                        return
                    run_date = remaining_args[1]
                    try:
                        from datetime import datetime
                        datetime.strptime(run_date, "%Y-%m-%d")
                    except ValueError:
                        await update.message.reply_text("日期格式错误，请使用 YYYY-MM-DD")
                        return
                    valid, hour, minute, err = schedule_manager.validate_time(remaining_args[2])
                    if not valid:
                        await update.message.reply_text(err)
                        return
                    name = " ".join(remaining_args[3:])

            else:
                # Legacy format: HH:MM name... (defaults to daily)
                schedule_type = SCHEDULE_TYPE_DAILY
                valid, hour, minute, err = schedule_manager.validate_time(remaining_args[0])
                if not valid:
                    await update.message.reply_text(t("SCHEDULE_ADD_INVALID_TIME"))
                    return
                name = " ".join(remaining_args[1:])

            if not name.strip():
                await update.message.reply_text("任务名称不能为空")
                return

            # Create task with placeholder prompt, initially DISABLED
            timezone = schedule_manager.get_user_timezone(user_id)
            success = schedule_manager.add_task(
                user_id=user_id,
                task_id=task_id,
                name=name,
                hour=hour,
                minute=minute,
                prompt="(Prompt not set yet)",
                enabled=False,
                schedule_type=schedule_type,
                weekdays=weekdays,
                month_day=month_day,
                interval_minutes=interval_minutes,
                run_date=run_date,
                max_runs=max_runs,
                start_time=start_time
            )

            if success:
                pending_schedule_prompts[user_id] = task_id
                # Format display info
                task = schedule_manager.get_task(user_id, task_id)
                schedule_str = schedule_manager.format_schedule_type(task) if task else schedule_type
                max_info = f"\n执行次数限制: {max_runs} 次" if max_runs else ""
                start_info = f"\n首次执行: {start_time}" if start_time else ""

                await update.message.reply_text(
                    f"任务 '{name}' 已创建\n"
                    f"ID: {task_id}\n"
                    f"周期: {schedule_str}\n"
                    f"时区: {timezone}{max_info}{start_info}\n\n"
                    f"请输入任务指令 (prompt):"
                )
            else:
                await update.message.reply_text(t("SCHEDULE_ADD_INVALID_ID"))

        elif subcommand == "del":
            # Delete task: /schedule del <id>
            if len(args) < 2:
                await update.message.reply_text(t("SCHEDULE_DEL_USAGE"))
                return

            task_id = args[1]
            if schedule_manager.delete_task(user_id, task_id):
                await update.message.reply_text(t("SCHEDULE_DEL_SUCCESS", task_id=task_id))
            else:
                await update.message.reply_text(t("SCHEDULE_DEL_NOT_FOUND", task_id=task_id))

        elif subcommand == "enable":
            if len(args) < 2:
                await update.message.reply_text("Usage: /schedule enable <task_id>")
                return
            task_id = args[1]
            if schedule_manager.enable_task(user_id, task_id):
                await update.message.reply_text(t("SCHEDULE_ENABLE_SUCCESS", task_id=task_id))
            else:
                await update.message.reply_text(t("SCHEDULE_TOGGLE_NOT_FOUND", task_id=task_id))

        elif subcommand == "disable":
            if len(args) < 2:
                await update.message.reply_text("Usage: /schedule disable <task_id>")
                return
            task_id = args[1]
            if schedule_manager.disable_task(user_id, task_id):
                await update.message.reply_text(t("SCHEDULE_DISABLE_SUCCESS", task_id=task_id))
            else:
                await update.message.reply_text(t("SCHEDULE_TOGGLE_NOT_FOUND", task_id=task_id))

        elif subcommand == "timezone":
            if len(args) < 2:
                # Show current timezone
                timezone = schedule_manager.get_user_timezone(user_id)
                await update.message.reply_text(t("SCHEDULE_TIMEZONE_CURRENT", timezone=timezone))
                return

            timezone = args[1]
            if schedule_manager.set_user_timezone(user_id, timezone):
                await update.message.reply_text(t("SCHEDULE_TIMEZONE_SUCCESS", timezone=timezone))
            else:
                await update.message.reply_text(t("SCHEDULE_TIMEZONE_INVALID", timezone=timezone))

        elif subcommand == "edit":
            if len(args) < 2:
                await update.message.reply_text("Usage: /schedule edit <task_id>")
                return

            task_id = args[1]
            prompt = schedule_manager.get_task_prompt(user_id, task_id)
            if prompt:
                pending_schedule_prompts[user_id] = task_id
                # Truncate prompt if too long
                display_prompt = prompt[:500] + "..." if len(prompt) > 500 else prompt
                await update.message.reply_text(
                    t("SCHEDULE_EDIT_PROMPT", task_id=task_id, prompt=display_prompt)
                )
            else:
                await update.message.reply_text(t("SCHEDULE_EDIT_NOT_FOUND", task_id=task_id))

        elif subcommand == "reset":
            # Reset run count and re-enable a task: /schedule reset <task_id>
            if len(args) < 2:
                await update.message.reply_text("Usage: /schedule reset <task_id>")
                return

            task_id = args[1]
            task = schedule_manager.get_task(user_id, task_id)
            if not task:
                await update.message.reply_text(f"任务 '{task_id}' 不存在")
                return

            success, err = schedule_manager.update_task(
                user_id=user_id,
                task_id=task_id,
                enabled=True,
                reset_run_count=True
            )

            if success:
                schedule_str = schedule_manager.format_schedule_type(task)
                max_info = f"/{task.max_runs}" if task.max_runs else "/∞"
                await update.message.reply_text(
                    f"任务 '{task_id}' 已重置\n"
                    f"执行计数: 0{max_info}\n"
                    f"周期: {schedule_str}\n"
                    f"状态: 🟢 已启用"
                )
            else:
                await update.message.reply_text(f"重置失败: {err}")

        elif subcommand == "info":
            # Show detailed task info: /schedule info <task_id>
            if len(args) < 2:
                await update.message.reply_text("Usage: /schedule info <task_id>")
                return

            task_id = args[1]
            task = schedule_manager.get_task(user_id, task_id)
            if not task:
                await update.message.reply_text(f"任务 '{task_id}' 不存在")
                return

            prompt = schedule_manager.get_task_prompt(user_id, task_id)
            timezone = schedule_manager.get_user_timezone(user_id)
            schedule_str = schedule_manager.format_schedule_type(task)
            run_count_str = schedule_manager.format_run_count(task)

            # Status
            if task.max_runs and task.run_count >= task.max_runs:
                status = "⏸️ 已完成 (达到执行上限)"
            elif task.enabled:
                status = "🟢 已启用"
            else:
                status = "🔴 已禁用"

            last_run = task.last_run[:19].replace("T", " ") if task.last_run else "从未执行"
            created = task.created_at[:19].replace("T", " ") if task.created_at else "未知"

            # Truncate prompt for display
            display_prompt = prompt[:800] + "..." if prompt and len(prompt) > 800 else (prompt or "(无)")

            info = (
                f"任务详情: {task_id}\n"
                f"{'='*30}\n"
                f"名称: {task.name}\n"
                f"周期: {schedule_str}\n"
                f"时区: {timezone}\n"
                f"状态: {status}\n"
                f"执行: {run_count_str} 次\n"
                f"上次执行: {last_run}\n"
                f"创建时间: {created}\n"
                f"{'='*30}\n"
                f"指令:\n{display_prompt}"
            )
            await update.message.reply_text(info)

        else:
            await update.message.reply_text(t("SCHEDULE_HELP"))

    # Track users waiting to confirm skill installation
    pending_skill_installs: dict[int, Path] = {}  # user_id -> zip_path

    async def skill_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /skill command for managing user skills"""
        user_id = update.effective_user.id

        if not can_access(user_id):
            await handle_unauthorized_user(update, context)
            return

        if not skill_manager:
            await update.message.reply_text("Skill feature not available")
            return

        args = context.args or []

        if not args:
            await update.message.reply_text(t("SKILL_HELP"))
            return

        subcommand = args[0].lower()

        if subcommand == "list":
            skills = skill_manager.get_user_skills(user_id)
            if not skills:
                await update.message.reply_text(t("SKILL_LIST_EMPTY"))
                return

            lines = [f"{t('SKILL_LIST_TITLE')}\n"]
            for skill in skills:
                lines.append(f"- {skill.name}")
                if skill.description:
                    lines.append(f"  {skill.description[:100]}")
                lines.append("")

            await update.message.reply_text("\n".join(lines))

        elif subcommand == "del":
            if len(args) < 2:
                await update.message.reply_text(t("SKILL_DEL_USAGE"))
                return

            skill_name = args[1]
            if skill_manager.delete_skill(user_id, skill_name):
                # Clear agent cache so skill removal takes effect
                if user_id in user_agents:
                    del user_agents[user_id]
                await update.message.reply_text(t("SKILL_DELETED", name=skill_name))
            else:
                await update.message.reply_text(t("SKILL_NOT_FOUND", name=skill_name))

        elif subcommand == "info":
            if len(args) < 2:
                await update.message.reply_text(t("SKILL_INFO_USAGE"))
                return

            skill_name = args[1]
            skill = skill_manager.get_skill(user_id, skill_name)
            if skill:
                content = skill.get_content()
                if len(content) > 3000:
                    content = content[:3000] + "\n...(truncated)"
                await update.message.reply_text(f"Skill: {skill.name}\n\n{content}")
            else:
                await update.message.reply_text(t("SKILL_NOT_FOUND", name=skill_name))

        else:
            await update.message.reply_text(t("SKILL_HELP"))

    async def admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id

        if not is_admin(user_id):
            await update.message.reply_text(t("NO_ADMIN_PERMISSION"))
            return

        args = context.args or []

        if not args:
            await update.message.reply_text(
                f"{t('ADMIN_HELP_TITLE')}\n\n"
                f"{t('ADMIN_USER_MGMT')}\n"
                f"{t('ADMIN_USERS')}\n"
                f"{t('ADMIN_QUOTA')}\n"
                f"{t('ADMIN_ENABLE')}\n"
                f"{t('ADMIN_DISABLE')}\n"
                f"{t('ADMIN_NOTE')}\n"
                f"{t('ADMIN_RETENTION')}\n\n"
                f"{t('ADMIN_SESSION_MGMT')}\n"
                f"{t('ADMIN_SESSIONS')}\n\n"
                f"{t('ADMIN_STATS_MGMT')}\n"
                f"{t('ADMIN_STATS')}\n"
                f"{t('ADMIN_USERSTATS')}\n"
                f"{t('ADMIN_HISTORY')}\n"
                f"{t('ADMIN_CLEANUP')}\n\n"
                "🎯 自定义命令管理\n"
                "/admin command - 查看命令管理帮助"
            )

        elif args[0] == 'users':
            users = user_manager.get_all_users_info()
            if not users:
                await update.message.reply_text(t("NO_USERS"))
                return

            text = f"{t('USER_LIST_TITLE')}\n\n"
            for u in users:
                status = "✅" if u['enabled'] else "❌"
                admin_mark = "👑" if u['admin'] else ""
                notes = f"({u['notes']})" if u['notes'] else ""
                storage = u['storage']
                text += (
                    f"{status}{admin_mark} {u['user_id']} {notes}\n"
                    f"   {t('STORAGE_LABEL_ADMIN')}: {storage['used_formatted']} / {storage['quota_formatted']}\n"
                    f"   {t('RETENTION_LABEL')}: {u['retention_days']} {t('DAYS')}\n"
                )
            await update.message.reply_text(text)

        elif args[0] == 'sessions':
            sessions = session_manager.get_all_sessions_info()
            if not sessions:
                await update.message.reply_text(t("NO_ACTIVE_SESSIONS"))
                return

            text = f"{t('ACTIVE_SESSIONS_TITLE')}\n\n"
            for s in sessions:
                text += (
                    f"{t('USER_LABEL')}: {s['user_id']}\n"
                    f"  {t('MESSAGES_LABEL')}: {s['message_count']}, "
                    f"{t('IDLE_LABEL')}: {s['last_active']}s\n"
                )
            await update.message.reply_text(text)

        elif args[0] == 'quota' and len(args) >= 3:
            try:
                target_user = int(args[1])
                quota_gb = float(args[2])
                if user_manager.set_user_quota(target_user, quota_gb):
                    await update.message.reply_text(t("QUOTA_SET_SUCCESS", user_id=target_user, quota=quota_gb))
                else:
                    await update.message.reply_text(t("OPERATION_FAILED"))
            except ValueError:
                await update.message.reply_text(t("PARAMETER_ERROR"))

        elif args[0] == 'enable' and len(args) >= 2:
            try:
                target_user = int(args[1])
                if user_manager.set_user_enabled(target_user, True):
                    await update.message.reply_text(t("USER_ENABLED", user_id=target_user))
                else:
                    await update.message.reply_text(t("OPERATION_FAILED"))
            except ValueError:
                await update.message.reply_text(t("PARAMETER_ERROR"))

        elif args[0] == 'disable' and len(args) >= 2:
            try:
                target_user = int(args[1])
                if user_manager.set_user_enabled(target_user, False):
                    await update.message.reply_text(t("USER_DISABLED", user_id=target_user))
                else:
                    await update.message.reply_text(t("OPERATION_FAILED"))
            except ValueError:
                await update.message.reply_text(t("PARAMETER_ERROR"))

        elif args[0] == 'note' and len(args) >= 3:
            try:
                target_user = int(args[1])
                notes = ' '.join(args[2:])
                if user_manager.set_user_notes(target_user, notes):
                    await update.message.reply_text(t("NOTE_SET_SUCCESS", user_id=target_user, note=notes))
                else:
                    await update.message.reply_text(t("OPERATION_FAILED"))
            except ValueError:
                await update.message.reply_text(t("PARAMETER_ERROR"))

        elif args[0] == 'retention' and len(args) >= 3:
            try:
                target_user = int(args[1])
                days = int(args[2])
                if user_manager.set_user_retention(target_user, days):
                    await update.message.reply_text(t("RETENTION_SET_SUCCESS", user_id=target_user, days=days))
                else:
                    await update.message.reply_text(t("OPERATION_FAILED"))
            except ValueError:
                await update.message.reply_text(t("PARAMETER_ERROR"))

        elif args[0] == 'stats':
            days = int(args[1]) if len(args) >= 2 else 7
            all_stats = user_manager.get_all_users_chat_stats(days)

            if not all_stats:
                await update.message.reply_text(t("NO_RECORDS_IN_DAYS", days=days))
                return

            text = f"{t('ALL_USERS_STATS_TITLE', days=days)}\n\n"
            for uid, stats in sorted(all_stats.items(), key=lambda x: x[1]['total'], reverse=True):
                config = user_manager.get_user_config(uid)
                name = config.notes or str(uid)
                text += (
                    f"📊 {name}\n"
                    f"   {t('TOTAL_LABEL')}: {stats['total']} {t('MESSAGES_UNIT')}, "
                    f"{t('DAILY_AVG_LABEL')}: {stats['daily_avg']} {t('MESSAGES_UNIT')}\n"
                    f"   {t('ERRORS_LABEL')}: {stats['errors']} {t('TIMES')}\n"
                )
            await update.message.reply_text(text)

        elif args[0] == 'userstats' and len(args) >= 2:
            try:
                target_user = int(args[1])
                days = int(args[2]) if len(args) >= 3 else 7
                daily_stats = user_manager.get_user_daily_stats(target_user, days)

                config = user_manager.get_user_config(target_user)
                name = config.notes or str(target_user)

                text = f"{t('USER_STATS_TITLE', name=name, days=days)}\n\n"
                for date, stats in daily_stats.items():
                    text += f"{date}: {stats['count']} {t('MESSAGES_UNIT')}"
                    if stats['errors'] > 0:
                        text += f" ({t('ERROR_LABEL')} {stats['errors']})"
                    text += "\n"

                # Add hourly distribution (today)
                hourly = user_manager.get_user_hourly_stats(target_user)
                active_hours = [h for h, c in hourly.items() if c > 0]
                if active_hours:
                    hour_suffix = t("HOUR_SUFFIX")
                    text += f"\n{t('TODAY_ACTIVE_HOURS')}: {', '.join(f'{h}{hour_suffix}' for h in sorted(active_hours))}"

                await update.message.reply_text(text)
            except ValueError:
                await update.message.reply_text(t("PARAMETER_ERROR"))

        elif args[0] == 'history' and len(args) >= 2:
            try:
                target_user = int(args[1])
                limit = int(args[2]) if len(args) >= 3 else 10
                records = user_manager.get_user_chat_history(target_user, limit=limit)

                if not records:
                    await update.message.reply_text(t("NO_HISTORY", user_id=target_user))
                    return

                config = user_manager.get_user_config(target_user)
                name = config.notes or str(target_user)

                text = f"{t('USER_HISTORY_TITLE', name=name, count=len(records))}\n\n"
                for r in records:
                    dt = datetime.fromtimestamp(r.timestamp)
                    time_str = dt.strftime('%m-%d %H:%M')
                    status = "❌" if r.is_error else "✅"
                    msg = r.user_message[:50] + '...' if len(r.user_message) > 50 else r.user_message
                    text += f"{status} [{time_str}] {msg}\n"

                if len(text) > 4000:
                    file_bytes = BytesIO(text.encode('utf-8'))
                    file_bytes.name = f"history_{target_user}.txt"
                    await update.message.reply_document(document=file_bytes, filename=f"history_{target_user}.txt")
                else:
                    await update.message.reply_text(text)
            except ValueError:
                await update.message.reply_text(t("PARAMETER_ERROR"))

        elif args[0] == 'cleanup':
            results = user_manager.cleanup_expired_history()
            if not results:
                await update.message.reply_text(t("NO_CLEANUP_NEEDED"))
            else:
                text = f"{t('CLEANUP_DONE')}\n"
                for uid, count in results.items():
                    config = user_manager.get_user_config(uid)
                    name = config.notes or str(uid)
                    text += f"  {name}: {t('DELETED_RECORDS', count=count)}\n"
                await update.message.reply_text(text)

        # ===== 自定义命令管理 =====
        elif args[0] == 'command' or args[0] == 'cmd':
            if not custom_command_manager:
                await update.message.reply_text("自定义命令功能未初始化")
                return

            if len(args) < 2:
                # 显示帮助
                await update.message.reply_text(
                    "🎯 自定义命令管理\n\n"
                    "/admin command list - 查看所有自定义命令\n"
                    "/admin command create <用户ID> <需求描述> - Agent 设计并创建命令\n"
                    "/admin command delete <命令名> - 删除命令\n"
                    "/admin command rename <旧名> <新名> - 重命名\n"
                    "/admin command info <命令名> - 查看命令详情\n"
                    "/admin command files <命令名> - 查看媒体文件列表\n\n"
                    "创建命令示例:\n"
                    "/admin command create 123456 发送早安语音给这个用户\n"
                    "/admin command create 123456 每天生成财务报告并发送\n\n"
                    "添加媒体文件:\n"
                    "发送 /<命令名> 后再发送语音/图片/文件即可添加\n\n"
                    "也可以直接对话创建:\n"
                    "\"帮我创建一个命令，给用户 123456 发送早安语音\""
                )
                return

            sub_cmd = args[1]

            if sub_cmd == 'list':
                commands = custom_command_manager.get_all_commands()
                if not commands:
                    await update.message.reply_text("暂无自定义命令")
                    return
                text = "🎯 自定义命令列表\n\n"
                for cmd in commands:
                    target_config = user_manager.get_user_config(cmd.target_user_id)
                    target_name = target_config.notes or target_config.first_name or str(cmd.target_user_id)
                    text += f"/{cmd.name} → {target_name}\n"
                    text += f"   {cmd.description}\n"
                    text += f"   类型: {cmd.command_type}\n\n"
                await update.message.reply_text(text)

            elif sub_cmd == 'create' and len(args) >= 4:
                # 让 Agent 来设计和创建命令
                try:
                    target_user = int(args[2])
                    # 剩余参数作为需求描述
                    requirement = ' '.join(args[3:])

                    target_config = user_manager.get_user_config(target_user)
                    target_name = target_config.notes or target_config.first_name or str(target_user)

                    # 构建给 Agent 的 prompt
                    agent_prompt = f"""请帮我创建一个自定义命令。

目标用户: {target_name} (ID: {target_user})
需求描述: {requirement}

请根据需求分析：
1. 确定合适的命令名称（英文，简短易记）
2. 确定命令类型：
   - random_media: 随机发送媒体文件（语音、图片、视频等）
   - agent_script: 由 Agent 执行的脚本命令
3. 如果是 agent_script 类型，设计执行脚本/提示词
4. 使用 custom_command_create 工具创建命令

创建完成后，告诉我命令的详细信息。"""

                    thinking_msg = await update.message.reply_text("🤔 正在设计命令...")

                    # 获取 Agent 并执行
                    agent = get_agent_for_user(user_id, context.bot)
                    resume_session_id = session_manager.get_session_id(user_id)

                    response = await agent.process_message(
                        agent_prompt,
                        resume_session_id
                    )

                    if response.session_id:
                        usage_stats = {
                            'input_tokens': response.input_tokens,
                            'output_tokens': response.output_tokens,
                            'cost_usd': response.cost_usd,
                            'turns': response.num_turns
                        }
                        existing_session = session_manager.get_session(user_id)
                        if existing_session:
                            session_manager.update_session(user_id, response.session_id, usage=usage_stats)
                        else:
                            session_manager.create_session(user_id, response.session_id)
                            session_manager.update_session(user_id, usage=usage_stats)

                    await thinking_msg.delete()

                    if response.text:
                        await send_long_message(update, response.text)

                except ValueError:
                    await update.message.reply_text("用户 ID 格式错误")
                except Exception as e:
                    logger.error(f"Agent 创建命令失败: {e}")
                    await update.message.reply_text(f"创建失败: {e}")

            elif sub_cmd == 'delete' and len(args) >= 3:
                cmd_name = args[2].lower().lstrip('/')
                success, msg = custom_command_manager.delete_command(cmd_name)
                await update.message.reply_text(msg)

            elif sub_cmd == 'rename' and len(args) >= 4:
                old_name = args[2].lower().lstrip('/')
                new_name = args[3].lower().lstrip('/')
                success, msg = custom_command_manager.rename_command(old_name, new_name)
                await update.message.reply_text(msg)

            elif sub_cmd == 'info' and len(args) >= 3:
                cmd_name = args[2].lower().lstrip('/')
                cmd = custom_command_manager.get_command(cmd_name)
                if not cmd:
                    await update.message.reply_text(f"命令 /{cmd_name} 不存在")
                    return

                target_config = user_manager.get_user_config(cmd.target_user_id)
                target_name = target_config.notes or target_config.first_name or str(cmd.target_user_id)
                creator_config = user_manager.get_user_config(cmd.created_by)
                creator_name = creator_config.notes or creator_config.first_name or str(cmd.created_by)

                text = f"📋 命令详情: /{cmd.name}\n\n"
                text += f"目标用户: {target_name} ({cmd.target_user_id})\n"
                text += f"描述: {cmd.description}\n"
                text += f"类型: {cmd.command_type}\n"
                text += f"创建者: {creator_name}\n"
                text += f"创建时间: {cmd.created_at}\n"
                text += f"配置: {cmd.config}\n"

                # 统计媒体文件
                files = custom_command_manager.list_media_files(cmd_name)
                text += f"\n媒体文件: {len(files)} 个"

                await update.message.reply_text(text)

            elif sub_cmd == 'files' and len(args) >= 3:
                cmd_name = args[2].lower().lstrip('/')
                files = custom_command_manager.list_media_files(cmd_name)
                if not files:
                    await update.message.reply_text(f"/{cmd_name} 暂无媒体文件")
                    return

                text = f"📁 /{cmd_name} 媒体文件\n\n"
                for f in files:
                    size_kb = f['size'] / 1024
                    last = f['last_sent'][:10] if f['last_sent'] else '未发送'
                    text += f"• {f['filename']}\n"
                    text += f"  {size_kb:.1f}KB | 发送{f['count']}次 | {last}\n"

                await update.message.reply_text(text)

            else:
                await update.message.reply_text("参数错误，使用 /admin command 查看帮助")

        else:
            await update.message.reply_text(t("UNKNOWN_COMMAND"))

    async def custom_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle custom commands (e.g., /yumi)"""
        user_id = update.effective_user.id
        if not can_access(user_id):
            await handle_unauthorized_user(update, context)
            return

        if not custom_command_manager:
            return False

        # 获取命令名
        message_text = update.message.text or ""
        if not message_text.startswith('/'):
            return False

        cmd_name = message_text.split()[0][1:].lower()  # 去掉 / 前缀

        # 检查是否是自定义命令
        cmd = custom_command_manager.get_command(cmd_name)
        if not cmd:
            return False

        # Admin 模式：random_media 类型进入添加媒体状态
        # agent_script 类型则执行脚本（脚本里可能有 Admin 专属逻辑）
        if is_admin(user_id) and cmd.command_type == "random_media":
            pending_media_commands[user_id] = cmd_name
            files = custom_command_manager.list_media_files(cmd_name)
            await update.message.reply_text(
                f"📤 准备为 /{cmd_name} 添加媒体文件\n\n"
                f"当前文件数: {len(files)}\n\n"
                f"现在发送语音/图片/文件即可添加\n"
                f"发送 /cancel 取消"
            )
            return True

        # 检查权限：非 Admin 用户必须是目标用户
        if not is_admin(user_id) and cmd.target_user_id != user_id:
            await update.message.reply_text("你没有权限使用这个命令")
            return True

        # 执行命令：随机发送媒体
        if cmd.command_type == "random_media":
            file_path, error = custom_command_manager.get_random_media(cmd_name)
            if error:
                await update.message.reply_text(f"❌ {error}")
                return True

            # 根据媒体类型发送
            media_type = cmd.config.get("media_type", "voice")
            try:
                if media_type == "voice":
                    await update.message.reply_voice(voice=open(file_path, 'rb'))
                elif media_type == "photo":
                    await update.message.reply_photo(photo=open(file_path, 'rb'))
                elif media_type == "video":
                    await update.message.reply_video(video=open(file_path, 'rb'))
                else:
                    await update.message.reply_document(document=open(file_path, 'rb'))
            except Exception as e:
                logger.error(f"Failed to send media for /{cmd_name}: {e}")
                await update.message.reply_text(f"发送失败: {e}")

        # 执行命令：Agent 脚本
        elif cmd.command_type == "agent_script":
            if not cmd.script:
                await update.message.reply_text(f"❌ 命令 /{cmd_name} 未设置执行脚本")
                return True

            # 获取命令参数（命令后面的文字）
            cmd_args = message_text[len(cmd_name) + 1:].strip()  # +1 for the / prefix

            # 构建给 Agent 的 prompt
            agent_prompt = f"""执行自定义命令 /{cmd_name}

当前用户 ID: {user_id}
目标用户 ID: {cmd.target_user_id}
命令创建者 ID: {cmd.created_by}
用户是否为 Admin: {is_admin(user_id)}

命令说明: {cmd.description}

执行脚本:
{cmd.script}

用户输入参数: {cmd_args if cmd_args else "(无)"}

请根据当前用户 ID 和脚本中的逻辑执行相应的任务。"""

            # 更新用户信息
            user = update.effective_user
            user_manager.update_user_info(user_id, user.username or "", user.first_name or "")

            # 获取或创建 Agent
            agent = get_agent_for_user(user_id, context.bot)

            # 获取 session
            session = session_manager.get_session(user_id)
            resume_session_id = session.session_id if session else None

            # 执行 Agent
            try:
                response = await agent.process_message(agent_prompt, resume_session_id)
                if response.session_id:
                    usage_stats = {
                        'input_tokens': response.input_tokens,
                        'output_tokens': response.output_tokens,
                        'cost_usd': response.cost_usd,
                        'turns': response.num_turns
                    }
                    existing_session = session_manager.get_session(user_id)
                    if existing_session:
                        session_manager.update_session(user_id, response.session_id, usage=usage_stats)
                    else:
                        session_manager.create_session(user_id, response.session_id)
                        session_manager.update_session(user_id, usage=usage_stats)
            except Exception as e:
                logger.error(f"Agent execution failed for /{cmd_name}: {e}")
                await update.message.reply_text(f"执行失败: {e}")

        return True

    async def handle_media_for_custom_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle media messages for adding to custom commands (admin only)"""
        user_id = update.effective_user.id

        # 检查是否有待添加媒体的命令
        if user_id not in pending_media_commands:
            return False

        cmd_name = pending_media_commands[user_id]

        # 检查是否取消
        if update.message.text and update.message.text.strip().lower() in ('/cancel', 'cancel', '取消'):
            del pending_media_commands[user_id]
            await update.message.reply_text("已取消添加媒体")
            return True

        # 获取媒体文件
        file_obj = None
        file_name = None

        if update.message.voice:
            file_obj = update.message.voice
            file_name = f"voice_{datetime.now().strftime('%Y%m%d_%H%M%S')}.ogg"
        elif update.message.audio:
            file_obj = update.message.audio
            file_name = update.message.audio.file_name or f"audio_{datetime.now().strftime('%Y%m%d_%H%M%S')}.mp3"
        elif update.message.photo:
            file_obj = update.message.photo[-1]  # 获取最大尺寸
            file_name = f"photo_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jpg"
        elif update.message.video:
            file_obj = update.message.video
            file_name = update.message.video.file_name or f"video_{datetime.now().strftime('%Y%m%d_%H%M%S')}.mp4"
        elif update.message.document:
            file_obj = update.message.document
            file_name = update.message.document.file_name or f"file_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

        if not file_obj:
            return False

        try:
            # 下载文件
            tg_file = await file_obj.get_file()
            temp_path = Path(tempfile.gettempdir()) / file_name
            await tg_file.download_to_drive(temp_path)

            # 添加到命令文件夹
            success, msg = custom_command_manager.add_media_file(cmd_name, temp_path, file_name)

            # 清理临时文件
            temp_path.unlink(missing_ok=True)

            if success:
                files = custom_command_manager.list_media_files(cmd_name)
                await update.message.reply_text(
                    f"✅ {msg}\n"
                    f"当前文件数: {len(files)}\n\n"
                    f"继续发送更多文件，或发送 /cancel 完成"
                )
            else:
                await update.message.reply_text(f"❌ {msg}")

        except Exception as e:
            logger.error(f"Failed to add media for /{cmd_name}: {e}")
            await update.message.reply_text(f"添加失败: {e}")

        return True

    async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle regular text messages - call Agent (with session resume support)"""
        user_id = update.effective_user.id

        if not can_access(user_id):
            await handle_unauthorized_user(update, context)
            return

        user_message = update.message.text or ""

        # 检查是否是 admin 添加媒体模式（取消命令）
        if user_id in pending_media_commands:
            if user_message.strip().lower() in ('/cancel', 'cancel', '取消'):
                del pending_media_commands[user_id]
                await update.message.reply_text("已取消添加媒体")
                return
            # 如果不是取消，提示用户发送媒体或取消
            await update.message.reply_text("请发送语音/图片/视频/文件，或发送 /cancel 取消")
            return

        # 更新用户信息（用户名可能会变化）
        user = update.effective_user
        info_changed = user_manager.update_user_info(user_id, user.username or "", user.first_name or "")
        # 如果用户信息变化，清除 agent 缓存以使用新的显示名称
        if info_changed and user_id in user_agents:
            del user_agents[user_id]

        # Check if user is inputting a schedule prompt
        if schedule_manager and user_id in pending_schedule_prompts:
            task_id = pending_schedule_prompts[user_id]

            # Check for cancel command
            if user_message.strip().lower() in ("/cancel", "cancel", "取消"):
                pending_schedule_prompts.pop(user_id)
                # Delete the task since prompt was never set
                schedule_manager.delete_task(user_id, task_id)
                await update.message.reply_text(t("SCHEDULE_PROMPT_CANCELLED", task_id=task_id))
                return

            # Save prompt and enable the task
            pending_schedule_prompts.pop(user_id)
            if schedule_manager.update_task_prompt(user_id, task_id, user_message):
                # Enable the task now that prompt is set
                schedule_manager.enable_task(user_id, task_id)
                await update.message.reply_text(t("SCHEDULE_PROMPT_SAVED", task_id=task_id))
            else:
                await update.message.reply_text(t("SCHEDULE_PROMPT_SAVE_FAILED", task_id=task_id))
            return

        # Check if user is confirming skill installation
        if skill_manager and user_id in pending_skill_installs:
            zip_path = pending_skill_installs[user_id]
            user_reply = user_message.strip().lower()

            if user_reply in ("install", "yes", "确认", "安装", "是"):
                pending_skill_installs.pop(user_id)
                await update.message.reply_text(t("SKILL_INSTALL_START"))

                success, message, result = skill_manager.install_skill_from_zip(user_id, zip_path)

                if success:
                    # Clear agent cache so new skill takes effect
                    if user_id in user_agents:
                        del user_agents[user_id]

                    await update.message.reply_text(
                        t("SKILL_INSTALL_SUCCESS",
                          name=result.skill_name,
                          description=result.skill_description or "")
                    )
                else:
                    error_msg = f"{t('SKILL_INSTALL_FAILED')}\n\n{message}"
                    if result and result.errors:
                        error_msg += f"\n\n{t('SKILL_VALIDATION_ERRORS')}\n"
                        for err in result.errors[:5]:  # Show first 5 errors
                            error_msg += f"- {err}\n"

                        # Add fix suggestions
                        suggestions = skill_manager.validator.suggest_fixes(result)
                        if suggestions:
                            error_msg += f"\n{t('SKILL_FIX_SUGGESTIONS')}\n"
                            for sug in suggestions[:3]:
                                error_msg += f"- {sug[:200]}\n"

                    await update.message.reply_text(error_msg)

                # Clean up zip file
                try:
                    zip_path.unlink()
                except Exception:
                    pass
                return

            elif user_reply in ("cancel", "no", "取消", "否"):
                pending_skill_installs.pop(user_id)
                try:
                    zip_path.unlink()
                except Exception:
                    pass
                await update.message.reply_text(t("SKILL_UPLOAD_CANCELLED"))
                return
            # If neither install nor cancel, continue to normal message processing

        # Get message handler for this user (handles 10-second merge window)
        msg_handler = await get_message_handler(user_id)
        
        async def send_progress():
            return await update.message.reply_text(f"🤔 {t('PROCESSING')}")
        
        async def do_process(text, upd, ctx, thinking_msg):
            await _process_user_message(text, upd, ctx, thinking_msg, user_id)
        
        await msg_handler.handle_message(
            text=user_message,
            update=update,
            context=context,
            process_func=do_process,
            send_progress=send_progress
        )
    
    async def _process_user_message(user_message: str, update: Update, context: ContextTypes.DEFAULT_TYPE, thinking_msg, user_id: int):
        """Internal function to process user message"""

        # Start typing indicator
        typing = TypingIndicator(context.bot, user_id)
        await typing.start()

        # Maybe add reaction to user's message (30% probability)
        asyncio.create_task(maybe_add_reaction(
            bot=context.bot,
            chat_id=user_id,
            message_id=update.message.message_id,
            user_message=user_message,
            api_config=api_config,
            probability=0.3
        ))

        # Create progress update callback (edit the same message)
        async def update_progress(status: str):
            try:
                await thinking_msg.edit_text(status)
            except Exception:
                pass

        try:
            # Get Agent client for user
            agent = get_agent_for_user(user_id, context.bot)

            # Get session ID (if exists)
            resume_session_id = session_manager.get_session_id(user_id)

            if resume_session_id:
                logger.info(f"User {user_id} resuming session: {resume_session_id[:8]}...")
            else:
                logger.info(f"User {user_id} starting new session")

            # Process message (with progress callback)
            response = await agent.process_message(
                user_message,
                resume_session_id,
                progress_callback=update_progress
            )

            # Check if session not found error, auto retry
            if response.is_error and response.error_message and "No conversation found" in response.error_message:
                logger.warning(f"User {user_id} session expired, clearing and retrying")
                session_manager.end_session(user_id)
                agent = get_agent_for_user(user_id, context.bot)
                response = await agent.process_message(
                    user_message,
                    None,
                    progress_callback=update_progress
                )

            # Update or create session with usage stats
            if response.session_id:
                usage_stats = {
                    'input_tokens': response.input_tokens,
                    'output_tokens': response.output_tokens,
                    'cost_usd': response.cost_usd,
                    'turns': response.num_turns
                }
                existing_session = session_manager.get_session(user_id)
                if existing_session:
                    session_manager.update_session(user_id, response.session_id, usage=usage_stats)
                else:
                    session_manager.create_session(user_id, response.session_id)
                    session_manager.update_session(user_id, usage=usage_stats)

                # Check if auto-compaction is needed (threshold: 150K tokens)
                if session_manager.needs_compaction(user_id, threshold_tokens=150000):
                    await _auto_compact_session(user_id, update)

            # Record chat history (JSON format)
            user_manager.add_chat_record(
                user_id=user_id,
                user_message=user_message,
                agent_response=response.text,
                session_id=response.session_id,
                is_error=response.is_error
            )

            # Record chat log (txt format for human reading)
            chat_logger.log_message(
                user_id=user_id,
                user_message=user_message,
                agent_response=response.text,
                session_id=response.session_id,
                is_error=response.is_error
            )

            # Stop typing indicator
            await typing.stop()

            # Delete progress message
            await thinking_msg.delete()

            # Send final response
            if response.text:
                await send_long_message(update, response.text)

        except Exception as e:
            # Stop typing indicator on error
            await typing.stop()
            error_str = str(e)
            is_session_error = ("exit code 1" in error_str or "No conversation found" in error_str) and resume_session_id
            if is_session_error:
                logger.warning(f"User {user_id} session expired (exception), clearing and retrying")
                session_manager.end_session(user_id)
                try:
                    agent = get_agent_for_user(user_id, context.bot)
                    response = await agent.process_message(
                        user_message,
                        None,
                        progress_callback=update_progress
                    )
                    if response.session_id:
                        session_manager.create_session(user_id, response.session_id)
                    user_manager.add_chat_record(
                        user_id=user_id,
                        user_message=user_message,
                        agent_response=response.text,
                        session_id=response.session_id,
                        is_error=response.is_error
                    )
                    chat_logger.log_message(
                        user_id=user_id,
                        user_message=user_message,
                        agent_response=response.text,
                        session_id=response.session_id,
                        is_error=response.is_error
                    )
                    await typing.stop()
                    await thinking_msg.delete()
                    if response.text:
                        await send_long_message(update, response.text)
                    return
                except Exception as retry_error:
                    await typing.stop()
                    logger.error(f"User {user_id} retry failed: {retry_error}")
                    user_manager.add_chat_record(
                        user_id=user_id,
                        user_message=user_message,
                        agent_response=None,
                        is_error=True
                    )
                    chat_logger.log_message(
                        user_id=user_id,
                        user_message=user_message,
                        agent_response=None,
                        is_error=True
                    )
                    await thinking_msg.edit_text(t("PROCESS_FAILED", error=str(retry_error)))
                    return
            logger.error(f"User {user_id} message processing failed: {e}")
            user_manager.add_chat_record(
                user_id=user_id,
                user_message=user_message,
                agent_response=None,
                is_error=True
            )
            chat_logger.log_message(
                user_id=user_id,
                user_message=user_message,
                agent_response=None,
                is_error=True
            )
            await thinking_msg.edit_text(t("PROCESS_FAILED", error=str(e)))

    async def handle_voice_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle voice messages - for adding to custom commands"""
        user_id = update.effective_user.id
        if not can_access(user_id):
            await handle_unauthorized_user(update, context)
            return

        # 检查是否是 admin 添加媒体模式
        if user_id in pending_media_commands:
            await handle_media_for_custom_command(update, context)
            return

        # 否则忽略语音消息（或可以交给 Agent 处理）
        await update.message.reply_text("收到语音消息，但暂不支持语音交互")

    async def handle_photo_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle photo messages - save to temp file and let Agent analyze via Read tool"""
        user_id = update.effective_user.id
        if not can_access(user_id):
            await handle_unauthorized_user(update, context)
            return

        # 检查是否是 admin 添加媒体模式
        if user_id in pending_media_commands:
            await handle_media_for_custom_command(update, context)
            return

        # 更新用户信息
        user = update.effective_user
        info_changed = user_manager.update_user_info(user_id, user.username or "", user.first_name or "")
        if info_changed and user_id in user_agents:
            del user_agents[user_id]

        # 发送处理中提示
        thinking_msg = await update.message.reply_text(f"🖼️ {t('PROCESSING')}")

        # Start typing indicator
        typing = TypingIndicator(context.bot, user_id)
        await typing.start()

        # Maybe add reaction to user's message (30% probability)
        caption = update.message.caption or ""
        if caption:
            asyncio.create_task(maybe_add_reaction(
                bot=context.bot,
                chat_id=user_id,
                message_id=update.message.message_id,
                user_message=caption,
                api_config=api_config,
                probability=0.3
            ))

        try:
            # 获取用户目录
            user_data_path = user_manager.get_user_data_path(user_id)
            temp_dir = user_data_path / ".temp"
            temp_dir.mkdir(parents=True, exist_ok=True)

            # 下载图片（取最高分辨率）
            photo = update.message.photo[-1]  # 最大尺寸
            file = await context.bot.get_file(photo.file_id)

            # 生成临时文件名
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            temp_file = temp_dir / f"photo_{timestamp}.jpg"

            # 下载到文件
            await file.download_to_drive(str(temp_file))

            # 获取 caption（用户随图片发送的文字）
            caption = update.message.caption or ""

            # 构建消息 - 告诉 Agent 图片位置，让它用 Read 工具查看
            if caption:
                user_message = f"""用户发送了一张图片，并附带消息："{caption}"

图片已保存到临时文件：{temp_file}

请使用 Read 工具查看这张图片，然后根据用户的消息进行回应。
注意：这是临时文件，分析完成后如果用户不需要保存，可以忽略它（会自动清理）。
如果用户要求保存图片，请移动到合适的文件夹（如 images/）。"""
            else:
                user_message = f"""用户发送了一张图片。

图片已保存到临时文件：{temp_file}

请使用 Read 工具查看这张图片，然后描述图片内容。
注意：这是临时文件，分析完成后如果用户不需要保存，可以忽略它（会自动清理）。"""

            # 创建进度回调
            async def update_progress(status: str):
                try:
                    await thinking_msg.edit_text(status)
                except Exception:
                    pass

            # 获取 Agent 并处理
            agent = get_agent_for_user(user_id, context.bot)
            resume_session_id = session_manager.get_session_id(user_id)

            if resume_session_id:
                logger.info(f"User {user_id} resuming session with image: {resume_session_id[:8]}...")
            else:
                logger.info(f"User {user_id} starting new session with image")

            # 处理消息
            response = await agent.process_message(
                user_message,
                resume_session_id,
                progress_callback=update_progress
            )

            # 处理 session 过期错误
            if response.is_error and response.error_message and "No conversation found" in response.error_message:
                logger.warning(f"User {user_id} session expired, clearing and retrying")
                session_manager.end_session(user_id)
                agent = get_agent_for_user(user_id, context.bot)
                response = await agent.process_message(
                    user_message,
                    None,
                    progress_callback=update_progress
                )

            # 更新 session with usage stats
            if response.session_id:
                usage_stats = {
                    'input_tokens': response.input_tokens,
                    'output_tokens': response.output_tokens,
                    'cost_usd': response.cost_usd,
                    'turns': response.num_turns
                }
                existing_session = session_manager.get_session(user_id)
                if existing_session:
                    session_manager.update_session(user_id, response.session_id, usage=usage_stats)
                else:
                    session_manager.create_session(user_id, response.session_id)
                    session_manager.update_session(user_id, usage=usage_stats)

            # 记录聊天历史
            display_message = f"[Image] {caption}" if caption else "[Image]"
            user_manager.add_chat_record(
                user_id=user_id,
                user_message=display_message,
                agent_response=response.text,
                session_id=response.session_id,
                is_error=response.is_error
            )

            chat_logger.log_message(
                user_id=user_id,
                user_message=display_message,
                agent_response=response.text,
                session_id=response.session_id,
                is_error=response.is_error
            )

            # Stop typing indicator
            await typing.stop()

            # 删除进度消息
            await thinking_msg.delete()

            # 发送回复
            if response.text:
                await send_long_message(update, response.text)

        except Exception as e:
            # Stop typing indicator on error
            await typing.stop()
            logger.error(f"User {user_id} photo processing failed: {e}")
            try:
                await thinking_msg.edit_text(t("PROCESS_FAILED", error=str(e)))
            except Exception:
                pass

    async def handle_video_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle video messages - for adding to custom commands"""
        user_id = update.effective_user.id
        if not can_access(user_id):
            await handle_unauthorized_user(update, context)
            return

        # 检查是否是 admin 添加媒体模式
        if user_id in pending_media_commands:
            await handle_media_for_custom_command(update, context)
            return

        # 否则忽略视频消息
        await update.message.reply_text("收到视频，但暂不支持视频分析")

    async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle file upload - save file and tell Agent"""
        user_id = update.effective_user.id

        if not can_access(user_id):
            await handle_unauthorized_user(update, context)
            return

        # 检查是否是 admin 添加媒体模式
        if user_id in pending_media_commands:
            await handle_media_for_custom_command(update, context)
            return

        # 更新用户信息（用户名可能会变化）
        user = update.effective_user
        info_changed = user_manager.update_user_info(user_id, user.username or "", user.first_name or "")
        # 如果用户信息变化，清除 agent 缓存以使用新的显示名称
        if info_changed and user_id in user_agents:
            del user_agents[user_id]

        document = update.message.document
        if not document:
            return

        # Send indicator
        thinking_msg = await update.message.reply_text(f"📥 {t('RECEIVING_FILE')}")

        # Start typing indicator
        typing = TypingIndicator(context.bot, user_id)
        await typing.start()

        # Maybe add reaction to user's message (30% probability)
        caption = update.message.caption or ""
        if caption:
            asyncio.create_task(maybe_add_reaction(
                bot=context.bot,
                chat_id=user_id,
                message_id=update.message.message_id,
                user_message=caption,
                api_config=api_config,
                probability=0.3
            ))

        try:
            # Get user directory
            user_data_path = user_manager.get_user_data_path(user_id)
            uploads_dir = user_data_path / "uploads"
            uploads_dir.mkdir(parents=True, exist_ok=True)

            # Download file
            file = await context.bot.get_file(document.file_id)
            file_name = document.file_name or f"file_{document.file_id}"
            file_path = uploads_dir / file_name

            await file.download_to_drive(str(file_path))

            # Get file size
            file_size = file_path.stat().st_size
            size_str = f"{file_size} bytes"
            if file_size > 1024:
                size_str = f"{file_size / 1024:.1f} KB"
            if file_size > 1024 * 1024:
                size_str = f"{file_size / (1024 * 1024):.1f} MB"

            # Check if this is a skill zip upload
            caption = update.message.caption or ""
            is_skill_upload = (
                skill_manager and
                file_name.lower().endswith('.zip') and
                ('skill' in file_name.lower() or 'skill' in caption.lower())
            )

            if is_skill_upload:
                # This looks like a skill package
                pending_skill_installs[user_id] = file_path
                await typing.stop()
                await thinking_msg.edit_text(
                    f"📦 {t('FILE_SAVED', name=file_name, size=size_str)}\n\n"
                    f"{t('SKILL_UPLOAD_HINT')}"
                )
                return

            # Update indicator
            await thinking_msg.edit_text(f"📥 {t('FILE_SAVED', name=file_name, size=size_str)}\n🤔 {t('PROCESSING')}")

            # Create progress update callback
            async def update_progress(status: str):
                try:
                    await thinking_msg.edit_text(f"📥 {file_name}\n{status}")
                except Exception:
                    pass

            # Build message for Agent
            caption = update.message.caption or ""
            caption_line = t("USER_CAPTION_LINE", caption=caption) if caption else ""
            user_message = t("FILE_UPLOAD_PROMPT",
                filename=file_name,
                size=size_str,
                caption_line=caption_line
            )

            # Get Agent and process
            agent = get_agent_for_user(user_id, context.bot)
            resume_session_id = session_manager.get_session_id(user_id)

            response = await agent.process_message(
                user_message,
                resume_session_id,
                progress_callback=update_progress
            )

            # Check if session not found error, auto retry
            if response.is_error and response.error_message and "No conversation found" in response.error_message:
                logger.warning(f"User {user_id} session expired, clearing and retrying")
                session_manager.end_session(user_id)
                agent = get_agent_for_user(user_id, context.bot)
                response = await agent.process_message(
                    user_message,
                    None,
                    progress_callback=update_progress
                )

            # Update session
            if response.session_id:
                usage_stats = {
                    'input_tokens': response.input_tokens,
                    'output_tokens': response.output_tokens,
                    'cost_usd': response.cost_usd,
                    'turns': response.num_turns
                }
                existing_session = session_manager.get_session(user_id)
                if existing_session:
                    session_manager.update_session(user_id, response.session_id, usage=usage_stats)
                else:
                    session_manager.create_session(user_id, response.session_id)
                    session_manager.update_session(user_id, usage=usage_stats)

            # Record chat history
            user_manager.add_chat_record(
                user_id=user_id,
                user_message=user_message,
                agent_response=response.text,
                session_id=response.session_id,
                is_error=response.is_error
            )

            # Stop typing indicator
            await typing.stop()

            # Delete progress message
            await thinking_msg.delete()

            # Send response
            if response.text:
                await send_long_message(update, response.text)

        except Exception as e:
            # Stop typing indicator on error
            await typing.stop()
            error_str = str(e)
            is_session_error = ("exit code 1" in error_str or "No conversation found" in error_str) and resume_session_id
            if is_session_error:
                logger.warning(f"User {user_id} session expired (exception), clearing and retrying")
                session_manager.end_session(user_id)
                try:
                    agent = get_agent_for_user(user_id, context.bot)
                    response = await agent.process_message(
                        user_message,
                        None,
                        progress_callback=update_progress
                    )
                    if response.session_id:
                        session_manager.create_session(user_id, response.session_id)
                    user_manager.add_chat_record(
                        user_id=user_id,
                        user_message=user_message,
                        agent_response=response.text,
                        session_id=response.session_id,
                        is_error=response.is_error
                    )
                    await thinking_msg.delete()
                    if response.text:
                        await send_long_message(update, response.text)
                    return
                except Exception as retry_error:
                    logger.error(f"User {user_id} retry failed: {retry_error}")
                    user_manager.add_chat_record(
                        user_id=user_id,
                        user_message=user_message,
                        agent_response=None,
                        is_error=True
                    )
                    await thinking_msg.edit_text(t("PROCESS_FILE_FAILED", error=str(retry_error)))
                    return
            logger.error(f"User {user_id} file processing failed: {e}")
            user_manager.add_chat_record(
                user_id=user_id,
                user_message=user_message,
                agent_response=None,
                is_error=True
            )
            await thinking_msg.edit_text(t("PROCESS_FILE_FAILED", error=str(e)))

    # Register handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("session", session_command))
    app.add_handler(CommandHandler("status", status_command))
    app.add_handler(CommandHandler("new", new_session_command))
    app.add_handler(CommandHandler("compact", compact_command))
    app.add_handler(CommandHandler("storage", storage_command))
    app.add_handler(CommandHandler("ls", ls))
    app.add_handler(CommandHandler("del", del_command))
    app.add_handler(CommandHandler("env", env_command))
    app.add_handler(CommandHandler("packages", packages_command))
    app.add_handler(CommandHandler("schedule", schedule_command))
    app.add_handler(CommandHandler("skill", skill_command))
    app.add_handler(CommandHandler("admin", admin_command))
    app.add_handler(CommandHandler("cancel", lambda u, c: handle_media_for_custom_command(u, c)))

    # Custom command handler (must be after system commands)
    # Use a filter to only match commands that exist in custom_command_manager
    async def check_custom_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Check and handle custom commands"""
        if not custom_command_manager:
            return
        text = update.message.text or ""
        if not text.startswith('/'):
            return
        cmd_name = text.split()[0][1:].lower()
        if custom_command_manager.command_exists(cmd_name):
            await custom_command_handler(update, context)

    # Create a filter for custom commands
    class CustomCommandFilter(filters.MessageFilter):
        def filter(self, message):
            if not custom_command_manager:
                return False
            text = message.text or ""
            if not text.startswith('/'):
                return False
            cmd_name = text.split()[0][1:].lower()
            return custom_command_manager.command_exists(cmd_name)

    app.add_handler(MessageHandler(CustomCommandFilter(), check_custom_command))

    # Media handlers for custom commands (admin adding media)
    app.add_handler(MessageHandler(filters.VOICE, handle_voice_message))
    app.add_handler(MessageHandler(filters.AUDIO, handle_voice_message))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo_message))
    app.add_handler(MessageHandler(filters.VIDEO, handle_video_message))

    # File upload handler
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))

    # Regular message handler (must be last)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
