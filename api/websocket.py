"""WebSocket manager for real-time updates."""

import asyncio
import logging
from typing import Dict, Set, Optional
from fastapi import WebSocket

logger = logging.getLogger(__name__)


class WebSocketManager:
    """Manages WebSocket connections per user for real-time updates."""

    def __init__(self):
        # user_id -> set of WebSocket connections
        self._connections: Dict[int, Set[WebSocket]] = {}
        self._lock = asyncio.Lock()

    async def connect(self, user_id: int, websocket: WebSocket):
        """
        Accept and register a WebSocket connection.

        Args:
            user_id: User ID
            websocket: WebSocket connection
        """
        await websocket.accept()
        async with self._lock:
            if user_id not in self._connections:
                self._connections[user_id] = set()
            self._connections[user_id].add(websocket)
            logger.info(f"WebSocket connected for user {user_id}, "
                       f"total connections: {len(self._connections[user_id])}")

    async def disconnect(self, user_id: int, websocket: WebSocket):
        """
        Unregister a WebSocket connection.

        Args:
            user_id: User ID
            websocket: WebSocket connection
        """
        async with self._lock:
            if user_id in self._connections:
                self._connections[user_id].discard(websocket)
                if not self._connections[user_id]:
                    del self._connections[user_id]
                logger.info(f"WebSocket disconnected for user {user_id}")

    def get_connection_count(self, user_id: int) -> int:
        """Get number of active connections for a user."""
        return len(self._connections.get(user_id, set()))

    def get_total_connections(self) -> int:
        """Get total number of active connections."""
        return sum(len(conns) for conns in self._connections.values())

    async def send_to_user(self, user_id: int, message: dict):
        """
        Send message to all connections of a user.

        Args:
            user_id: User ID
            message: Message dict to send
        """
        async with self._lock:
            connections = self._connections.get(user_id, set()).copy()

        if not connections:
            return

        # Send to all connections, removing failed ones
        failed = []
        for ws in connections:
            try:
                await ws.send_json(message)
            except Exception as e:
                logger.debug(f"Failed to send to WebSocket: {e}")
                failed.append(ws)

        # Clean up failed connections
        if failed:
            async with self._lock:
                if user_id in self._connections:
                    for ws in failed:
                        self._connections[user_id].discard(ws)

    async def broadcast_task_update(
        self,
        user_id: int,
        task_id: str,
        status: str,
        result: Optional[str] = None
    ):
        """
        Broadcast task status update to a user.

        Args:
            user_id: User ID
            task_id: Task ID
            status: New task status
            result: Task result (if completed)
        """
        await self.send_to_user(user_id, {
            "type": "task_update",
            "data": {
                "task_id": task_id,
                "status": status,
                "result": result
            }
        })

    async def broadcast_task_created(
        self,
        user_id: int,
        task_id: str,
        description: str
    ):
        """
        Broadcast new task creation to a user.

        Args:
            user_id: User ID
            task_id: Task ID
            description: Task description
        """
        await self.send_to_user(user_id, {
            "type": "task_created",
            "data": {
                "task_id": task_id,
                "description": description
            }
        })

    async def broadcast_schedule_executed(
        self,
        user_id: int,
        task_id: str,
        run_count: int,
        next_run: Optional[str] = None
    ):
        """
        Broadcast schedule execution to a user.

        Args:
            user_id: User ID
            task_id: Schedule task ID
            run_count: Current run count
            next_run: Next scheduled run time (ISO format)
        """
        await self.send_to_user(user_id, {
            "type": "schedule_executed",
            "data": {
                "task_id": task_id,
                "run_count": run_count,
                "next_run": next_run
            }
        })

    async def broadcast_storage_update(
        self,
        user_id: int,
        used_bytes: int,
        quota_bytes: int
    ):
        """
        Broadcast storage update to a user.

        Args:
            user_id: User ID
            used_bytes: Used storage in bytes
            quota_bytes: Total quota in bytes
        """
        await self.send_to_user(user_id, {
            "type": "storage_update",
            "data": {
                "used_bytes": used_bytes,
                "quota_bytes": quota_bytes
            }
        })


# Global singleton instance
ws_manager = WebSocketManager()
