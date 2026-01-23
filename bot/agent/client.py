"""Agent client wrapper - manages interaction with Claude Agent"""

import logging
from typing import Callable, Awaitable, Any, Dict, Tuple, Optional
from pathlib import Path
from dataclasses import dataclass

from claude_agent_sdk import (
    ClaudeSDKClient,
    ClaudeAgentOptions,
    create_sdk_mcp_server,
    AssistantMessage,
    TextBlock,
    ToolUseBlock,
    ResultMessage,
    HookMatcher,
    HookContext
)

from .tools import create_telegram_tools, set_tool_config
from ..i18n import t, get_tool_display_name
from ..file_tracker import FileTracker, send_tracked_files
from ..prompt_builder import build_system_prompt, get_fallback_prompt
from ..bash_safety import check_bash_safety, SafetyLevel

logger = logging.getLogger(__name__)


@dataclass
class AgentResponse:
    """Agent response result"""
    text: Optional[str]  # Final text response
    session_id: Optional[str]  # Session ID (for resume)
    is_error: bool = False
    error_message: Optional[str] = None
    # Usage statistics
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    num_turns: int = 0


class TelegramAgentClient:
    """
    Wraps Claude Agent SDK for Telegram Bot interaction.
    Supports multi-user isolation, session resume, and Sub Agent mode.
    """

    def __init__(
        self,
        user_id: int,
        working_directory: str,
        send_message_callback: Callable[[str], Awaitable[None]],
        send_file_callback: Callable[[str, str | None], Awaitable[bool]],
        check_quota_callback: Callable[[int], tuple[bool, str]] | None = None,
        delegate_callback: Callable[[str, str], Awaitable[Optional[str]]] | None = None,
        delegate_review_callback: Callable[[str, str, str], Awaitable[Optional[str]]] | None = None,
        env_vars: Dict[str, str] | None = None,
        storage_info: dict | None = None,
        model: str | None = None,
        mistral_api_key: str | None = None,
        is_sub_agent: bool = False,
        custom_skills_content: str | None = None,
        schedule_manager: Any | None = None,
        task_manager: Any | None = None,
        user_display_name: str | None = None,
        custom_command_manager: Any | None = None,
        admin_user_ids: list[int] | None = None,
        context_summary: str | None = None
    ):
        """
        Initialize Agent client.

        Args:
            user_id: User ID
            working_directory: Agent working directory (user-specific)
            send_message_callback: Callback to send Telegram messages
            send_file_callback: Callback to send Telegram files
            check_quota_callback: Callback to check storage quota
            delegate_callback: Callback to delegate tasks to Sub Agents
            delegate_review_callback: Callback to delegate tasks with automatic quality review
            env_vars: User environment variables
            storage_info: User storage info
            model: Claude model name
            mistral_api_key: Mistral API key (for PDF conversion, not exposed to Agent)
            is_sub_agent: Whether this is a Sub Agent (won't send messages to user)
            custom_skills_content: User's custom skills content to append to system prompt
            schedule_manager: Schedule manager for scheduled task operations
            task_manager: Task manager for Sub Agent task operations
            user_display_name: User's display name (username or first_name) for friendly addressing
            custom_command_manager: Custom command manager for admin operations
            admin_user_ids: List of admin user IDs for permission checks
            context_summary: Previous conversation summary (from /compact)
        """
        self.user_id = user_id
        self.working_directory = Path(working_directory).resolve()
        self.send_message_callback = send_message_callback
        self.send_file_callback = send_file_callback
        self.check_quota_callback = check_quota_callback
        self.delegate_callback = delegate_callback
        self.delegate_review_callback = delegate_review_callback
        self.env_vars = env_vars or {}
        self.storage_info = storage_info or {}
        self.model = model
        self.is_sub_agent = is_sub_agent
        self.custom_skills_content = custom_skills_content or ""
        self.schedule_manager = schedule_manager
        self.task_manager = task_manager
        self.user_display_name = user_display_name or ""
        self.custom_command_manager = custom_command_manager
        self.admin_user_ids = admin_user_ids or []
        self.context_summary = context_summary or ""

        # Initialize file tracker for tracking new files during task execution
        self.file_tracker = FileTracker(self.working_directory)

        # Set tool config (API key won't be exposed to Agent)
        set_tool_config(
            mistral_api_key=mistral_api_key,
            working_directory=str(self.working_directory),
            delegate_callback=delegate_callback,
            delegate_review_callback=delegate_review_callback,
            schedule_manager=schedule_manager,
            user_id=user_id,
            task_manager=task_manager,
            custom_command_manager=custom_command_manager,
            admin_user_ids=admin_user_ids
        )

        # Create custom tools
        # Sub Agents don't get message/file sending or delegation capabilities
        if is_sub_agent:
            self.telegram_tools = create_telegram_tools(
                send_message_callback=self._noop_send_message,
                send_file_callback=self._noop_send_file
            )
        else:
            self.telegram_tools = create_telegram_tools(
                send_message_callback=send_message_callback,
                send_file_callback=send_file_callback
            )

        # Create MCP server
        self.mcp_server = create_sdk_mcp_server(
            name="telegram",
            version="1.0.0",
            tools=self.telegram_tools
        )

    async def _noop_send_message(self, text: str) -> None:
        """No-op message sender for Sub Agents"""
        logger.debug(f"Sub Agent message (not sent to user): {text[:100]}...")

    async def _noop_send_file(self, path: str, caption: str | None) -> bool:
        """No-op file sender for Sub Agents"""
        logger.debug(f"Sub Agent file (not sent to user): {path}")
        return True

    def _is_path_safe(self, path_str: str) -> bool:
        """Check if path is within the user's working directory."""
        if not path_str:
            return True
        try:
            # Resolve the path (handles .., symlinks, etc.)
            requested_path = Path(path_str).resolve()
            # Check if it's within working directory
            requested_path.relative_to(self.working_directory)
            return True
        except ValueError:
            # Path is outside working directory
            return False

    def _get_path_from_tool_input(self, tool_name: str, tool_input: Dict[str, Any]) -> Optional[str]:
        """Extract file path from tool input based on tool type."""
        if tool_name == 'Read':
            return tool_input.get('file_path')
        elif tool_name == 'Write':
            return tool_input.get('file_path')
        elif tool_name == 'Edit':
            return tool_input.get('file_path')
        elif tool_name == 'Glob':
            return tool_input.get('path')
        elif tool_name == 'Grep':
            return tool_input.get('path')
        return None

    async def _pre_tool_hook(
        self,
        input_data: Dict[str, Any],
        tool_use_id: str | None,
        context: HookContext
    ) -> Dict[str, Any]:
        """Pre-tool hook - for path security, quota checking, and Bash safety."""
        tool_name = input_data.get('tool_name', '')
        tool_input = input_data.get('tool_input', {})

        # Bash safety check - CRITICAL
        if tool_name == 'Bash':
            command = tool_input.get('command', '')
            result = check_bash_safety(command, self.working_directory, self.user_id)

            if not result.is_safe:
                logger.warning(
                    f"User {self.user_id} Bash DENIED: {result.reason} - "
                    f"command: {command[:100]}..."
                )
                return {
                    'hookSpecificOutput': {
                        'hookEventName': 'PreToolUse',
                        'permissionDecision': 'deny',
                        'permissionDecisionReason': f'Bash command blocked: {result.reason}'
                    }
                }

            # Log allowed commands for monitoring
            if result.level == SafetyLevel.UNKNOWN:
                logger.info(f"User {self.user_id} Bash (monitored): {command[:100]}...")

        # Security check: validate path is within working directory
        if tool_name in ('Read', 'Write', 'Edit', 'Glob', 'Grep'):
            path_str = self._get_path_from_tool_input(tool_name, tool_input)
            if path_str and not self._is_path_safe(path_str):
                logger.warning(f"User {self.user_id} attempted to access path outside working directory: {path_str}")
                return {
                    'hookSpecificOutput': {
                        'hookEventName': 'PreToolUse',
                        'permissionDecision': 'deny',
                        'permissionDecisionReason': 'Access denied: path is outside your working directory'
                    }
                }

        # Quota check for write operations
        if tool_name in ('Write', 'Edit') and self.check_quota_callback:
            if tool_name == 'Write':
                content = tool_input.get('content', '')
                estimated_size = len(content.encode('utf-8'))
            else:
                new_string = tool_input.get('new_string', '')
                old_string = tool_input.get('old_string', '')
                estimated_size = max(0, len(new_string.encode('utf-8')) - len(old_string.encode('utf-8')))

            allowed, message = self.check_quota_callback(estimated_size)
            if not allowed:
                logger.warning(f"User {self.user_id} quota insufficient: {message}")
                return {
                    'hookSpecificOutput': {
                        'hookEventName': 'PreToolUse',
                        'permissionDecision': 'deny',
                        'permissionDecisionReason': f'Storage quota exceeded: {message}'
                    }
                }

        return {}

    def _create_options(
        self,
        resume_session_id: str | None = None,
        custom_system_prompt: str | None = None
    ) -> ClaudeAgentOptions:
        """
        Create Agent options.

        Args:
            resume_session_id: Session ID to resume (None for new session)
            custom_system_prompt: Custom system prompt (for Sub Agents)
        """
        # Always enable hooks for path security, quota check, and Bash safety
        hooks = {
            'PreToolUse': [
                HookMatcher(
                    matcher='Read|Write|Edit|Glob|Grep|Bash',
                    hooks=[self._pre_tool_hook]
                )
            ]
        }

        # Build allowed tools list
        allowed_tools = [
            "mcp__telegram__web_search",
            "mcp__telegram__web_fetch",
            "mcp__telegram__pdf_to_markdown",
            "mcp__telegram__delete_file",
            "mcp__telegram__compress_folder",
            "Read",
            "Write",
            "Edit",
            "Glob",
            "Grep",
            "Skill",
            "Bash",  # Enabled with safety checks via PreToolUse hook
        ]

        # Main Agent can send messages/files, delegate tasks, and manage schedules
        if not self.is_sub_agent:
            allowed_tools.extend([
                "mcp__telegram__send_telegram_message",
                "mcp__telegram__send_telegram_file",
                "mcp__telegram__delegate_task",
                "mcp__telegram__delegate_and_review",
                "mcp__telegram__schedule_list",
                "mcp__telegram__schedule_get",
                "mcp__telegram__schedule_create",
                "mcp__telegram__schedule_update",
                "mcp__telegram__schedule_delete",
                # Custom command management tools
                "mcp__telegram__custom_command_list",
                "mcp__telegram__custom_command_get",
                "mcp__telegram__custom_command_create",
                "mcp__telegram__custom_command_update",
                "mcp__telegram__custom_command_delete",
                "mcp__telegram__custom_command_rename",
                "mcp__telegram__custom_command_list_media",
                # Task management tools
                "mcp__telegram__get_task_result",
                "mcp__telegram__list_tasks",
            ])

        system_prompt = custom_system_prompt if custom_system_prompt else self._get_system_prompt()

        options = ClaudeAgentOptions(
            cwd=str(self.working_directory),
            mcp_servers={"telegram": self.mcp_server},
            allowed_tools=allowed_tools,
            # Bash is now allowed with safety checks via PreToolUse hook
            permission_mode="acceptEdits",
            system_prompt=system_prompt,
            env=self.env_vars,
            hooks=hooks,
            model=self.model,
            setting_sources=["user", "project"],
        )

        # Set resume if session ID provided
        if resume_session_id:
            options.resume = resume_session_id

        return options

    def _get_system_prompt(self) -> str:
        """Get system prompt (built from modular components)"""
        try:
            prompt = build_system_prompt(
                user_id=self.user_id,
                user_display_name=self.user_display_name,
                working_directory=str(self.working_directory),
                storage_info=self.storage_info,
                context_summary=self.context_summary,
                custom_skills_content=self.custom_skills_content
            )
            return prompt
        except Exception as e:
            logger.error(f"Failed to build system prompt: {e}")
            return get_fallback_prompt(self.user_id, str(self.working_directory))

    async def process_message(
        self,
        user_message: str,
        resume_session_id: str | None = None,
        progress_callback: Callable[[str], Awaitable[None]] | None = None,
        context_id: str | None = None,
        custom_system_prompt: str | None = None,
        track_files: bool = True
    ) -> AgentResponse:
        """
        Process user message.

        Args:
            user_message: Message from user
            resume_session_id: Session ID to resume (None for new session)
            progress_callback: Callback for progress updates
            context_id: Context ID for task tracking
            custom_system_prompt: Custom system prompt (for Sub Agents)
            track_files: Whether to track and send new files after completion

        Returns:
            AgentResponse with response text and session ID
        """
        # Start file tracking before processing
        if track_files and not self.is_sub_agent:
            self.file_tracker.start()

        options = self._create_options(resume_session_id, custom_system_prompt)
        final_response = None
        session_id = None
        is_error = False
        error_message = None
        step_count = 0
        # Usage statistics
        result_input_tokens = 0
        result_output_tokens = 0
        result_cost = 0.0
        result_turns = 0

        # Tool name icons for progress display
        tool_icons = {
            "Read": "📖",
            "Write": "✍️",
            "Edit": "✏️",
            "Glob": "🔍",
            "Grep": "🔎",
            "Skill": "🎯",
            "mcp__telegram__send_telegram_message": "💬",
            "mcp__telegram__send_telegram_file": "📤",
            "mcp__telegram__web_search": "🌐",
            "mcp__telegram__web_fetch": "📥",
            "mcp__telegram__pdf_to_markdown": "📄",
            "mcp__telegram__delete_file": "🗑️",
            "mcp__telegram__compress_folder": "📦",
            "mcp__telegram__delegate_task": "🔀",
        }

        agent_type = "Sub Agent" if self.is_sub_agent else "Main Agent"

        try:
            async with ClaudeSDKClient(options=options) as client:
                await client.query(user_message)

                async for message in client.receive_response():
                    if isinstance(message, AssistantMessage):
                        for block in message.content:
                            if isinstance(block, TextBlock):
                                final_response = block.text
                            elif isinstance(block, ToolUseBlock):
                                # Tool call - update progress
                                step_count += 1
                                tool_name = block.name
                                icon = tool_icons.get(tool_name, "🔧")
                                display_name = get_tool_display_name(tool_name)
                                tool_display = f"{icon} {display_name}"

                                # Only main agent reports progress to user
                                if progress_callback and not self.is_sub_agent:
                                    try:
                                        await progress_callback(t("STEP_PROGRESS", step=step_count, tool=tool_display))
                                    except Exception as e:
                                        logger.debug(f"Progress callback failed: {e}")

                    elif isinstance(message, ResultMessage):
                        # Get session ID and usage info
                        session_id = message.session_id
                        result_cost = message.total_cost_usd or 0
                        result_turns = message.num_turns or 0

                        # Extract token usage from usage dict
                        usage_data = message.usage or {}
                        result_input_tokens = usage_data.get('input_tokens', 0)
                        result_output_tokens = usage_data.get('output_tokens', 0)

                        logger.info(
                            f"User {self.user_id} {agent_type} completed: "
                            f"session={session_id[:8] if session_id else 'N/A'}..., "
                            f"turns={result_turns}, "
                            f"tokens={result_input_tokens}+{result_output_tokens}, "
                            f"cost=${result_cost:.4f}"
                        )

                        if message.is_error:
                            is_error = True
                            error_message = message.result
                            logger.error(f"User {self.user_id} {agent_type} error: {message.result}")

        except Exception as e:
            logger.error(f"User {self.user_id} {agent_type} processing failed: {e}")
            is_error = True
            error_message = str(e)
            # Only main agent sends error messages to user
            if not self.is_sub_agent:
                try:
                    await self.send_message_callback(t("PROCESS_FAILED", error=str(e)))
                except Exception:
                    pass

        # Send tracked files after processing (main agent only)
        if track_files and not self.is_sub_agent:
            try:
                new_files = self.file_tracker.get_new_files()
                if new_files:
                    sent_count = await send_tracked_files(
                        files=new_files,
                        working_dir=self.working_directory,
                        send_file_callback=self.send_file_callback,
                        send_message_callback=self.send_message_callback
                    )
                    if sent_count > 0:
                        logger.info(f"User {self.user_id}: Sent {sent_count} new files")
            except Exception as e:
                logger.error(f"Failed to send tracked files: {e}")

        return AgentResponse(
            text=final_response,
            session_id=session_id,
            is_error=is_error,
            error_message=error_message,
            input_tokens=result_input_tokens,
            output_tokens=result_output_tokens,
            cost_usd=result_cost,
            num_turns=result_turns
        )


def create_sub_agent(
    user_id: int,
    working_directory: str,
    env_vars: Dict[str, str] | None = None,
    model: str | None = None,
    mistral_api_key: str | None = None,
    send_file_callback: Callable[[str, str | None], Awaitable[bool]] | None = None
) -> TelegramAgentClient:
    """
    Factory function to create a Sub Agent.

    Sub Agents cannot send messages to users directly, but CAN send files.
    """
    async def noop_send(_): pass
    async def noop_file(_, __): return True

    return TelegramAgentClient(
        user_id=user_id,
        working_directory=working_directory,
        send_message_callback=noop_send,
        send_file_callback=send_file_callback or noop_file,
        env_vars=env_vars,
        model=model,
        mistral_api_key=mistral_api_key,
        is_sub_agent=True
    )
