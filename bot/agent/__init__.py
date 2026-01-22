"""Agent module - Claude Agent SDK integration"""

from .client import TelegramAgentClient, create_sub_agent, AgentResponse
from .tools import create_telegram_tools, set_tool_config
from .task_manager import TaskManager, SubAgentTask, TaskStatus
from .orchestrator import UserAgentOrchestrator, get_orchestrator, AgentState
from .message_handler import UserMessageHandler, get_message_handler
from .review import ReviewAgent, ReviewResult, create_review_callback

__all__ = [
    'TelegramAgentClient',
    'create_sub_agent',
    'AgentResponse',
    'create_telegram_tools',
    'set_tool_config',
    'TaskManager',
    'SubAgentTask',
    'TaskStatus',
    'UserAgentOrchestrator',
    'get_orchestrator',
    'AgentState',
    'UserMessageHandler',
    'get_message_handler',
    'ReviewAgent',
    'ReviewResult',
    'create_review_callback',
]
