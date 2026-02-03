"""Authentication utilities for Telegram Mini App."""

import hashlib
import hmac
import json
import time
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional
from urllib.parse import parse_qs

from jose import JWTError, jwt
from fastapi import HTTPException, status

logger = logging.getLogger(__name__)

# JWT Configuration
JWT_ALGORITHM = "HS256"
JWT_EXPIRATION_HOURS = 24


class TelegramAuth:
    """Handles Telegram initData validation and JWT token management."""

    def __init__(self, bot_token: str, jwt_secret: Optional[str] = None):
        """
        Initialize TelegramAuth.

        Args:
            bot_token: Telegram bot token for initData validation
            jwt_secret: Secret key for JWT signing (defaults to bot_token hash)
        """
        self.bot_token = bot_token
        # Use a hash of bot_token as JWT secret if not provided
        self.jwt_secret = jwt_secret or hashlib.sha256(bot_token.encode()).hexdigest()

    def validate_init_data(self, init_data: str, max_age: int = 86400) -> dict:
        """
        Validate Telegram Mini App initData.

        Args:
            init_data: The initData string from Telegram
            max_age: Maximum age of initData in seconds (default 24h)

        Returns:
            Parsed user data if valid

        Raises:
            HTTPException: If validation fails
        """
        try:
            # Parse the initData
            parsed = parse_qs(init_data)

            # Extract hash
            received_hash = parsed.get('hash', [None])[0]
            if not received_hash:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Missing hash in initData"
                )

            # Check auth_date
            auth_date_str = parsed.get('auth_date', [None])[0]
            if not auth_date_str:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Missing auth_date in initData"
                )

            auth_date = int(auth_date_str)
            current_time = int(time.time())

            if current_time - auth_date > max_age:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="initData expired"
                )

            # Build data-check-string (sorted, excluding hash)
            data_check_parts = []
            for key in sorted(parsed.keys()):
                if key != 'hash':
                    value = parsed[key][0]
                    data_check_parts.append(f"{key}={value}")
            data_check_string = '\n'.join(data_check_parts)

            # Compute HMAC
            # secret_key = HMAC-SHA256(bot_token, "WebAppData")
            secret_key = hmac.new(
                b"WebAppData",
                self.bot_token.encode(),
                hashlib.sha256
            ).digest()

            computed_hash = hmac.new(
                secret_key,
                data_check_string.encode(),
                hashlib.sha256
            ).hexdigest()

            # Compare hashes (constant time comparison)
            if not hmac.compare_digest(computed_hash, received_hash):
                logger.warning("initData hash validation failed")
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid hash"
                )

            # Extract user data
            user_json = parsed.get('user', ['{}'])[0]
            user_data = json.loads(user_json)

            if not user_data.get('id'):
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Missing user ID in initData"
                )

            return {
                "user_id": user_data.get("id"),
                "username": user_data.get("username"),
                "first_name": user_data.get("first_name"),
                "last_name": user_data.get("last_name"),
                "language_code": user_data.get("language_code"),
                "auth_date": auth_date
            }

        except HTTPException:
            raise
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse user JSON in initData: {e}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid user data format"
            )
        except Exception as e:
            logger.error(f"initData validation error: {e}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"Validation error: {str(e)}"
            )

    def create_access_token(self, user_data: dict) -> str:
        """
        Create a JWT access token.

        Args:
            user_data: User data to encode in the token

        Returns:
            JWT token string
        """
        now = datetime.now(timezone.utc)
        expire = now + timedelta(hours=JWT_EXPIRATION_HOURS)

        payload = {
            "user_id": user_data["user_id"],
            "username": user_data.get("username"),
            "first_name": user_data.get("first_name"),
            "exp": expire,
            "iat": now,
        }

        token = jwt.encode(payload, self.jwt_secret, algorithm=JWT_ALGORITHM)
        return token

    def verify_token(self, token: str) -> dict:
        """
        Verify and decode a JWT token.

        Args:
            token: JWT token string

        Returns:
            Decoded token payload

        Raises:
            HTTPException: If token is invalid or expired
        """
        try:
            payload = jwt.decode(
                token,
                self.jwt_secret,
                algorithms=[JWT_ALGORITHM]
            )
            user_id = payload.get("user_id")
            if user_id is None:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid token payload"
                )
            return payload

        except JWTError as e:
            logger.warning(f"JWT verification failed: {e}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired token"
            )


def validate_init_data_dev(init_data: str) -> dict:
    """
    Development mode validation (accepts mock data).

    Args:
        init_data: The initData string (can be mock data in dev mode)

    Returns:
        Parsed user data
    """
    if init_data.startswith("dev_"):
        # Parse dev mode data: dev_123456789_username
        parts = init_data.split("_")
        if len(parts) >= 2:
            try:
                user_id = int(parts[1])
                return {
                    "user_id": user_id,
                    "username": parts[2] if len(parts) > 2 else "dev_user",
                    "first_name": "Dev",
                    "last_name": "User",
                    "auth_date": int(time.time())
                }
            except ValueError:
                pass

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid dev mode initData"
    )
