"""Authentication routes."""

import logging
from fastapi import APIRouter, HTTPException, status, Depends
from pydantic import BaseModel

from ..dependencies import get_deps, get_current_user

logger = logging.getLogger(__name__)

router = APIRouter()


class AuthRequest(BaseModel):
    """Authentication request body."""
    init_data: str


class AuthResponse(BaseModel):
    """Authentication response."""
    token: str
    user: dict


class UserResponse(BaseModel):
    """Current user response."""
    user_id: int
    username: str | None
    first_name: str | None


@router.post("", response_model=AuthResponse)
async def authenticate(request: AuthRequest):
    """
    Authenticate with Telegram initData and receive JWT token.

    This endpoint validates the initData from Telegram Mini App
    and returns a JWT token for subsequent API calls.
    """
    deps = get_deps()

    # Validate initData
    try:
        if deps.dev_mode and request.init_data.startswith("dev_"):
            # Development mode with mock data
            from ..auth import validate_init_data_dev
            user_data = validate_init_data_dev(request.init_data)
        else:
            # Production mode - validate with Telegram
            user_data = deps.telegram_auth.validate_init_data(request.init_data)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Authentication error: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication failed"
        )

    user_id = user_data["user_id"]

    # Check if user exists in our system
    if not deps.user_manager.user_exists(user_id):
        # Check if new users are allowed
        if not deps.allow_new_users:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="New user registration is disabled"
            )
        # Could auto-register here if desired
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User not registered. Please start the bot first."
        )

    # Check if user is enabled
    if not deps.user_manager.is_user_enabled(user_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is disabled"
        )

    # Create JWT token
    token = deps.telegram_auth.create_access_token(user_data)

    logger.info(f"User {user_id} authenticated via Mini App")

    return AuthResponse(
        token=token,
        user={
            "user_id": user_id,
            "username": user_data.get("username"),
            "first_name": user_data.get("first_name"),
            "last_name": user_data.get("last_name")
        }
    )


@router.get("/me", response_model=UserResponse)
async def get_current_user_info(user: dict = Depends(get_current_user)):
    """
    Get current authenticated user info.

    Requires Bearer token authentication.
    """
    return UserResponse(
        user_id=user["user_id"],
        username=user.get("username"),
        first_name=user.get("first_name")
    )
