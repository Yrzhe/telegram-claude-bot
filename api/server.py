"""FastAPI application server for Mini App."""

import logging
from typing import Callable, Optional
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .auth import TelegramAuth
from .websocket import ws_manager
from .dependencies import Dependencies, set_dependencies, get_deps
from .routes import auth, files, tasks, schedules, subagents

logger = logging.getLogger(__name__)


def create_api_app(
    user_manager,
    session_manager,
    schedule_manager,
    get_task_manager: Callable,
    bot_token: str,
    allow_new_users: bool = True,
    dev_mode: bool = False,
    static_dir: Optional[str] = None
) -> FastAPI:
    """
    Create and configure the FastAPI application.

    Args:
        user_manager: UserManager instance
        session_manager: SessionManager instance
        schedule_manager: ScheduleManager instance
        get_task_manager: Function(user_id) -> TaskManager
        bot_token: Telegram bot token for auth
        allow_new_users: Whether new user registration is allowed
        dev_mode: Enable development mode
        static_dir: Path to static files (frontend build)

    Returns:
        Configured FastAPI application
    """

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        """Application lifespan handler."""
        logger.info("Mini App API starting...")
        yield
        logger.info("Mini App API shutting down...")

    # Create FastAPI app
    app = FastAPI(
        title="Telegram Bot Mini App API",
        description="API for Telegram Mini App dashboard",
        version="1.0.0",
        lifespan=lifespan,
        docs_url="/api/docs" if dev_mode else None,
        redoc_url="/api/redoc" if dev_mode else None,
        openapi_url="/api/openapi.json" if dev_mode else None
    )

    # Initialize auth
    telegram_auth = TelegramAuth(bot_token)

    # Initialize dependencies
    deps = Dependencies(
        telegram_auth=telegram_auth,
        user_manager=user_manager,
        session_manager=session_manager,
        schedule_manager=schedule_manager,
        get_task_manager=get_task_manager,
        allow_new_users=allow_new_users,
        dev_mode=dev_mode
    )
    set_dependencies(deps)

    # CORS middleware - restrict in production
    allowed_origins = ["*"] if dev_mode else [
        "https://web.telegram.org",
        "https://t.me",
    ]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Include routers
    app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
    app.include_router(files.router, prefix="/api/files", tags=["files"])
    app.include_router(tasks.router, prefix="/api/tasks", tags=["tasks"])
    app.include_router(schedules.router, prefix="/api/schedules", tags=["schedules"])
    app.include_router(subagents.router, prefix="/api/subagents", tags=["subagents"])

    # WebSocket endpoint
    @app.websocket("/api/ws")
    async def websocket_endpoint(
        websocket: WebSocket,
        token: str = Query(...)
    ):
        """WebSocket endpoint for real-time updates."""
        try:
            # Verify token
            user_data = telegram_auth.verify_token(token)
            user_id = user_data["user_id"]

            # Connect
            await ws_manager.connect(user_id, websocket)

            try:
                while True:
                    # Receive and handle messages
                    data = await websocket.receive_json()
                    msg_type = data.get("type")

                    if msg_type == "ping":
                        await websocket.send_json({"type": "pong"})
                    elif msg_type == "subscribe":
                        # Could implement event subscription logic here
                        events = data.get("events", [])
                        await websocket.send_json({
                            "type": "subscribed",
                            "events": events
                        })

            except WebSocketDisconnect:
                pass
            finally:
                await ws_manager.disconnect(user_id, websocket)

        except Exception as e:
            logger.warning(f"WebSocket connection failed: {e}")
            await websocket.close(code=4001)

    # Health check endpoint
    @app.get("/api/health")
    async def health_check():
        """Health check endpoint."""
        return {
            "status": "healthy",
            "websocket_connections": ws_manager.get_total_connections()
        }

    # Mount static files if provided
    if static_dir:
        app.mount("/", StaticFiles(directory=static_dir, html=True), name="static")

    return app


async def run_api_server(app: FastAPI, host: str = "127.0.0.1", port: int = 8000):
    """
    Run the API server using uvicorn.

    Args:
        app: FastAPI application
        host: Host to bind to
        port: Port to listen on
    """
    import uvicorn

    config = uvicorn.Config(
        app,
        host=host,
        port=port,
        log_level="info",
        access_log=False
    )
    server = uvicorn.Server(config)
    await server.serve()
