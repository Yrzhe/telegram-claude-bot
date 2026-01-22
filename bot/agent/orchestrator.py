"""User Agent Orchestrator - Manages main Agent and Sub Agents for a user"""

import asyncio
import logging
import uuid
from dataclasses import dataclass, field
from typing import Optional, Callable, Awaitable, Any, Dict, List
from enum import Enum
from datetime import datetime

from .task_manager import TaskManager, SubAgentTask, TaskStatus
from ..i18n import t

logger = logging.getLogger(__name__)


class AgentState(Enum):
    """Main Agent state"""
    IDLE = "idle"                    # Can accept new messages
    PROCESSING = "processing"        # Processing user message
    WAITING_SUB_AGENTS = "waiting"   # Waiting for Sub Agents to complete


@dataclass
class MessageContext:
    """Context for a user message being processed"""
    message_id: str
    text: str
    timestamp: datetime = field(default_factory=datetime.now)
    cancel_event: asyncio.Event = field(default_factory=asyncio.Event)
    
    def request_cancel(self):
        self.cancel_event.set()
    
    def is_cancelled(self) -> bool:
        return self.cancel_event.is_set()


class UserAgentOrchestrator:
    """
    Orchestrates the main Agent and Sub Agents for a single user.
    
    Features:
    - 10-second message merge window
    - Message buffering when busy
    - Sub Agent delegation
    - Task cancellation on new messages within window
    """
    
    MESSAGE_MERGE_WINDOW = 10.0  # seconds
    
    def __init__(
        self,
        user_id: int,
        create_main_agent: Callable[[], Any],
        create_sub_agent: Callable[[], Any],
        send_message: Callable[[str], Awaitable[None]],
        send_progress: Callable[[str], Awaitable[None]],
    ):
        """
        Initialize orchestrator for a user.
        
        Args:
            user_id: Telegram user ID
            create_main_agent: Factory function to create main Agent
            create_sub_agent: Factory function to create Sub Agent
            send_message: Callback to send message to user
            send_progress: Callback to update progress indicator
        """
        self.user_id = user_id
        self._create_main_agent = create_main_agent
        self._create_sub_agent = create_sub_agent
        self._send_message = send_message
        self._send_progress = send_progress
        
        self._state = AgentState.IDLE
        self._state_lock = asyncio.Lock()
        
        # Message buffer for when agent is busy
        self._message_buffer: List[str] = []
        self._buffer_lock = asyncio.Lock()
        
        # Current processing context
        self._current_context: Optional[MessageContext] = None
        
        # Task manager for Sub Agents
        self._task_manager = TaskManager(user_id)
        
        # Window timer
        self._window_task: Optional[asyncio.Task] = None
        self._window_expired = asyncio.Event()
        
        # Main processing task
        self._main_task: Optional[asyncio.Task] = None
        
        # Results storage
        self._pending_sub_results: List[Dict[str, Any]] = []

    @property
    def state(self) -> AgentState:
        return self._state

    @property
    def is_busy(self) -> bool:
        return self._state != AgentState.IDLE

    @property
    def active_sub_agents(self) -> int:
        return self._task_manager.active_task_count

    async def handle_user_message(self, text: str) -> None:
        """
        Handle an incoming user message.
        
        This is the main entry point for user messages.
        """
        async with self._state_lock:
            if self._state == AgentState.IDLE:
                # Start new processing
                await self._start_processing(text)
            elif self._state == AgentState.PROCESSING:
                # Check if within merge window
                if self._current_context and not self._window_expired.is_set():
                    # Within window - cancel current and merge
                    await self._cancel_and_merge(text)
                else:
                    # Outside window - buffer the message
                    await self._buffer_message(text)
            elif self._state == AgentState.WAITING_SUB_AGENTS:
                # Agent is waiting for Sub Agents - buffer message
                await self._buffer_message(text)

    async def _start_processing(self, text: str) -> None:
        """Start processing a new message"""
        message_id = str(uuid.uuid4())[:8]
        self._current_context = MessageContext(
            message_id=message_id,
            text=text
        )
        self._state = AgentState.PROCESSING
        self._window_expired.clear()
        
        logger.info(f"User {self.user_id} starting processing: {text[:50]}...")
        
        # Start the merge window timer
        self._window_task = asyncio.create_task(self._window_timer())
        
        # Start main processing task
        self._main_task = asyncio.create_task(
            self._process_message(self._current_context)
        )

    async def _window_timer(self) -> None:
        """Timer for the message merge window"""
        await asyncio.sleep(self.MESSAGE_MERGE_WINDOW)
        self._window_expired.set()
        logger.debug(f"User {self.user_id} merge window expired")

    async def _cancel_and_merge(self, new_text: str) -> None:
        """Cancel current processing and merge with new message"""
        if not self._current_context:
            return
        
        old_text = self._current_context.text
        old_message_id = self._current_context.message_id
        
        logger.info(
            f"User {self.user_id} received new message within window, "
            f"cancelling current task and merging"
        )
        
        # Cancel current context
        self._current_context.request_cancel()
        
        # Cancel Sub Agents triggered by this message
        cancelled = await self._task_manager.cancel_tasks_by_parent(old_message_id)
        if cancelled:
            logger.info(f"Cancelled {cancelled} Sub Agent tasks")
        
        # Cancel window timer
        if self._window_task and not self._window_task.done():
            self._window_task.cancel()
        
        # Cancel main task
        if self._main_task and not self._main_task.done():
            self._main_task.cancel()
            try:
                await self._main_task
            except asyncio.CancelledError:
                pass
        
        # Merge messages
        merged_text = f"{old_text}\n{new_text}"
        
        # Notify user
        try:
            await self._send_progress(t("MESSAGE_MERGED"))
        except Exception:
            pass
        
        # Start fresh processing with merged message
        message_id = str(uuid.uuid4())[:8]
        self._current_context = MessageContext(
            message_id=message_id,
            text=merged_text
        )
        self._window_expired.clear()
        
        # Restart window timer
        self._window_task = asyncio.create_task(self._window_timer())
        
        # Restart main processing
        self._main_task = asyncio.create_task(
            self._process_message(self._current_context)
        )

    async def _buffer_message(self, text: str) -> None:
        """Add message to buffer for later processing"""
        async with self._buffer_lock:
            self._message_buffer.append(text)
            logger.info(
                f"User {self.user_id} message buffered "
                f"(buffer size: {len(self._message_buffer)})"
            )

    async def _process_message(self, context: MessageContext) -> None:
        """
        Main message processing logic.
        
        This runs the main Agent and handles Sub Agent results.
        """
        try:
            # Wait for window to expire before allowing Sub Agent creation
            # But start processing immediately
            agent = self._create_main_agent()
            
            # Process with main Agent
            # The agent can call delegate_task which creates Sub Agents
            response = await self._run_main_agent(agent, context)
            
            if context.is_cancelled():
                logger.info(f"User {self.user_id} context was cancelled, aborting")
                return
            
            # Check if there are pending Sub Agents
            if self._task_manager.has_pending_tasks(context.message_id):
                async with self._state_lock:
                    self._state = AgentState.WAITING_SUB_AGENTS
                
                # Notify user we're waiting
                try:
                    active_count = self._task_manager.active_task_count
                    await self._send_progress(
                        t("WAITING_SUB_AGENTS", count=active_count)
                    )
                except Exception:
                    pass
                
                # Wait for all Sub Agents
                sub_results = await self._task_manager.wait_for_tasks(
                    context.message_id,
                    timeout=300.0
                )
                
                if context.is_cancelled():
                    return
                
                # Process Sub Agent results with main Agent
                if sub_results:
                    await self._process_sub_results(agent, context, sub_results)
            
            # Send final response if we have one
            if response and response.text:
                await self._send_message(response.text)
            
        except asyncio.CancelledError:
            logger.info(f"User {self.user_id} processing cancelled")
            raise
        except Exception as e:
            logger.error(f"User {self.user_id} processing error: {e}")
            try:
                await self._send_message(t("PROCESS_FAILED", error=str(e)))
            except Exception:
                pass
        finally:
            # Transition to IDLE and check buffer
            await self._finish_processing()

    async def _run_main_agent(self, agent, context: MessageContext):
        """Run the main Agent with the user message"""
        # This will be implemented based on the actual agent interface
        # For now, return a placeholder
        try:
            response = await agent.process_message(
                context.text,
                context_id=context.message_id,
                delegate_callback=self._create_delegate_callback(context.message_id)
            )
            return response
        except Exception as e:
            logger.error(f"Main agent error: {e}")
            raise

    async def _process_sub_results(
        self,
        agent,
        context: MessageContext,
        sub_results: List[Dict[str, Any]]
    ) -> None:
        """Process Sub Agent results with main Agent"""
        async with self._state_lock:
            self._state = AgentState.PROCESSING
        
        # Format Sub Agent results for main Agent
        results_text = t("SUB_AGENT_RESULTS_HEADER") + "\n\n"
        for result in sub_results:
            results_text += f"### {result['description']}\n"
            results_text += f"{result['result']}\n\n"
        
        # Send to main Agent for synthesis
        try:
            synthesis_prompt = t("SYNTHESIZE_RESULTS_PROMPT", results=results_text)
            response = await agent.process_message(
                synthesis_prompt,
                context_id=context.message_id
            )
            if response and response.text:
                await self._send_message(response.text)
        except Exception as e:
            logger.error(f"Failed to synthesize Sub Agent results: {e}")

    def _create_delegate_callback(
        self,
        parent_message_id: str
    ) -> Callable[[str, str], Awaitable[Optional[str]]]:
        """Create a callback for the main Agent to delegate tasks"""
        
        async def delegate_task(description: str, prompt: str) -> Optional[str]:
            """
            Delegate a task to a Sub Agent.
            
            Args:
                description: Short description of the task
                prompt: Full prompt for the Sub Agent
                
            Returns:
                Task ID if created, None if limit reached
            """
            if not self._task_manager.can_create_task:
                return None
            
            async def executor(task: SubAgentTask) -> str:
                """Execute the Sub Agent task"""
                sub_agent = self._create_sub_agent()
                response = await sub_agent.process_message(prompt)
                return response.text if response else ""
            
            task = await self._task_manager.create_task(
                parent_message_id=parent_message_id,
                description=description,
                executor=executor
            )
            
            return task.task_id if task else None
        
        return delegate_task

    async def _finish_processing(self) -> None:
        """Finish processing and check for buffered messages"""
        async with self._state_lock:
            self._state = AgentState.IDLE
            self._current_context = None
        
        # Clean up old tasks
        self._task_manager.cleanup_old_tasks()
        
        # Check buffer
        async with self._buffer_lock:
            if self._message_buffer:
                # Merge all buffered messages
                merged = "\n".join(self._message_buffer)
                self._message_buffer.clear()
                logger.info(
                    f"User {self.user_id} processing buffered messages"
                )
                # Process merged buffer (release lock first)
        
        # If we had buffered messages, process them
        if merged := getattr(self, '_temp_merged', None):
            delattr(self, '_temp_merged')
            await self.handle_user_message(merged)
        else:
            # Check again in case buffer was filled during our check
            async with self._buffer_lock:
                if self._message_buffer:
                    merged = "\n".join(self._message_buffer)
                    self._message_buffer.clear()
            
            if merged:
                await self.handle_user_message(merged)

    async def shutdown(self) -> None:
        """Shutdown the orchestrator and cancel all tasks"""
        logger.info(f"Shutting down orchestrator for user {self.user_id}")
        
        # Cancel current processing
        if self._current_context:
            self._current_context.request_cancel()
        
        # Cancel all Sub Agents
        await self._task_manager.cancel_all_tasks()
        
        # Cancel timers and tasks
        if self._window_task and not self._window_task.done():
            self._window_task.cancel()
        if self._main_task and not self._main_task.done():
            self._main_task.cancel()

    def get_status(self) -> Dict[str, Any]:
        """Get current status of the orchestrator"""
        return {
            "state": self._state.value,
            "buffer_size": len(self._message_buffer),
            "sub_agents": self._task_manager.get_status_summary(),
            "current_message": (
                self._current_context.text[:50] + "..."
                if self._current_context else None
            )
        }


# Global registry of orchestrators per user
_orchestrators: Dict[int, UserAgentOrchestrator] = {}
_registry_lock = asyncio.Lock()


async def get_orchestrator(
    user_id: int,
    create_main_agent: Callable[[], Any],
    create_sub_agent: Callable[[], Any],
    send_message: Callable[[str], Awaitable[None]],
    send_progress: Callable[[str], Awaitable[None]],
) -> UserAgentOrchestrator:
    """Get or create an orchestrator for a user"""
    async with _registry_lock:
        if user_id not in _orchestrators:
            _orchestrators[user_id] = UserAgentOrchestrator(
                user_id=user_id,
                create_main_agent=create_main_agent,
                create_sub_agent=create_sub_agent,
                send_message=send_message,
                send_progress=send_progress,
            )
        return _orchestrators[user_id]


async def remove_orchestrator(user_id: int) -> None:
    """Remove and shutdown an orchestrator"""
    async with _registry_lock:
        if user_id in _orchestrators:
            await _orchestrators[user_id].shutdown()
            del _orchestrators[user_id]
