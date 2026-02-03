"""FastAPI dependency injection."""

import logging
from typing import Callable, Optional
from fastapi import Depends, HTTPException, status, Query
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from .auth import TelegramAuth

logger = logging.getLogger(__name__)

# Security scheme
security = HTTPBearer(auto_error=False)


class Dependencies:
    """
    Dependency container for FastAPI routes.

    Holds references to shared managers and provides dependency injection.
    """

    def __init__(
        self,
        telegram_auth: TelegramAuth,
        user_manager,
        session_manager,
        schedule_manager,
        get_task_manager: Callable,
        allow_new_users: bool = True,
        dev_mode: bool = False
    ):
        """
        Initialize dependencies.

        Args:
            telegram_auth: TelegramAuth instance
            user_manager: UserManager instance
            session_manager: SessionManager instance
            schedule_manager: ScheduleManager instance
            get_task_manager: Function to get TaskManager for a user
            allow_new_users: Whether new user registration is allowed
            dev_mode: Enable development mode (relaxed auth)
        """
        self.telegram_auth = telegram_auth
        self.user_manager = user_manager
        self.session_manager = session_manager
        self.schedule_manager = schedule_manager
        self.get_task_manager = get_task_manager
        self.allow_new_users = allow_new_users
        self.dev_mode = dev_mode

    async def get_current_user(
        self,
        credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)
    ) -> dict:
        """
        Dependency to get the current authenticated user from JWT token.

        Args:
            credentials: HTTP Bearer credentials

        Returns:
            User data dict with user_id, username, etc.

        Raises:
            HTTPException: If authentication fails
        """
        if credentials is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Missing authentication token",
                headers={"WWW-Authenticate": "Bearer"}
            )

        token = credentials.credentials
        user_data = self.telegram_auth.verify_token(token)

        # Verify user exists in our system
        user_id = user_data["user_id"]
        if not self.user_manager.user_exists(user_id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="User not registered"
            )

        # Check if user is enabled
        if not self.user_manager.is_user_enabled(user_id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="User account is disabled"
            )

        return user_data

    async def get_current_user_id(
        self,
        user: dict = None
    ) -> int:
        """
        Dependency to get just the user ID.

        Args:
            user: User data from get_current_user

        Returns:
            User ID
        """
        # This will be called with the result of get_current_user
        if user is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication required"
            )
        return user["user_id"]

    def get_user_working_directory(self, user_id: int) -> str:
        """
        Get the working directory for a user.

        Args:
            user_id: User ID

        Returns:
            Path to user's base directory (parent of data/)
        """
        # get_user_data_path returns users/{id}/data, we need users/{id}
        data_path = self.user_manager.get_user_data_path(user_id)
        return str(data_path.parent)

    def get_user_task_manager(self, user_id: int):
        """
        Get TaskManager for a user.

        Args:
            user_id: User ID

        Returns:
            TaskManager instance
        """
        return self.get_task_manager(user_id)


# Global dependencies instance (set by create_api_app)
_deps: Optional[Dependencies] = None


def set_dependencies(deps: Dependencies):
    """Set the global dependencies instance."""
    global _deps
    _deps = deps


def get_deps() -> Dependencies:
    """Get the global dependencies instance."""
    if _deps is None:
        raise RuntimeError("Dependencies not initialized")
    return _deps


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)
) -> dict:
    """Dependency to get current authenticated user."""
    deps = get_deps()
    return await deps.get_current_user(credentials)


async def get_current_user_id(
    user: dict = Depends(get_current_user)
) -> int:
    """Dependency to get current user ID."""
    return user["user_id"]


def get_user_manager():
    """Dependency to get UserManager."""
    return get_deps().user_manager


def get_session_manager():
    """Dependency to get SessionManager."""
    return get_deps().session_manager


def get_schedule_manager():
    """Dependency to get ScheduleManager."""
    return get_deps().schedule_manager


def get_task_manager_for_user(user_id: int = Depends(get_current_user_id)):
    """Dependency to get TaskManager for current user."""
    return get_deps().get_user_task_manager(user_id)


def get_working_directory(user_id: int = Depends(get_current_user_id)) -> str:
    """Dependency to get working directory for current user."""
    return get_deps().get_user_working_directory(user_id)
