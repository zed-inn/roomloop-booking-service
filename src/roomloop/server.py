import asyncio
import sys
from typing import Any

import uvicorn
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from roomloop.api.v1.router import register_api_v1_routes
from roomloop.config.database import DatabaseConnection
from roomloop.config.env import env
from roomloop.config.fastapi import FastApiApp
from roomloop.modules.audit.model import AuditLogModel  # noqa: F401
from roomloop.modules.bookings.model import BookingModel, SeriesModel  # noqa: F401
from roomloop.modules.rooms.model import RoomModel  # noqa: F401
from roomloop.seeding.seeder import DatabaseSeeder
from roomloop.shared.models.base import Base
from roomloop.shared.services.logger import app_logger


class ListenerOpts(BaseModel):
    """runtime listener network binding options for uvicorn server"""

    model_config = {"frozen": True, "extra": "forbid"}

    host: str = Field(default="localhost", min_length=1)
    port: int = Field(default=8095, ge=1, le=65535)


class Server:
    """orchestrates application dependencies, uvicorn listener, and server lifecycle"""

    def __init__(
        self,
        fastapi_app: FastApiApp | None = None,
        database: DatabaseConnection | None = None,
        listener_opts: dict[str, Any] | None = None,
    ) -> None:
        opts = listener_opts or {"host": env.HOST, "port": env.PORT}
        self.listener_opts: ListenerOpts = ListenerOpts.model_validate(opts)
        self.fastapi: FastApiApp = (
            fastapi_app if fastapi_app is not None else FastApiApp()
        )
        self.database: DatabaseConnection = (
            database if database is not None else DatabaseConnection()
        )
        self._uvicorn_server: uvicorn.Server | None = None
        self._is_shutting_down: bool = False
        self.setup_app()

    def setup_app(self) -> None:
        """mounts routes, health check, and database state onto fastapi instance"""
        self.fastapi.app.state.db = self.database

        @self.fastapi.app.get("/health", tags=["system"])
        async def health() -> JSONResponse:
            is_healthy: bool = self.database.check_connection()
            status_code: int = 200 if is_healthy else 503
            return JSONResponse(
                status_code=status_code,
                content={
                    "status": "ok" if is_healthy else "degraded",
                    "environment": env.ENVIRONMENT,
                    "database": "connected" if is_healthy else "disconnected",
                },
            )

        register_api_v1_routes(self.fastapi.app, db=self.database)

    async def start_prerequisites(self) -> None:
        """initializes database connection, ensures schema tables exist, and seeds prototype data"""
        app_logger.info("[Server] Starting prerequisites...")
        self.database.connect()
        if not self.database.check_connection():
            raise RuntimeError("[Server] Database health check failed during boot")

        # ensure orm model tables exist in database
        Base.metadata.create_all(bind=self.database.engine)
        # execute initial seeding for prototype rooms
        seeder = DatabaseSeeder(self.database)
        seeder.seed_all()

        app_logger.info("[Server] Prerequisites successfully initialized")

    async def shutdown(self) -> None:
        """gracefully shuts down server and releases database connection pool"""
        if self._is_shutting_down:
            return
        self._is_shutting_down = True

        app_logger.info("[Server] Shutdown sequence initiated...")
        if self._uvicorn_server is not None:
            self._uvicorn_server.should_exit = True

        if self.database.is_connected:
            self.database.disconnect()

        app_logger.info("[Server] Shutdown complete")

    async def start(self) -> None:
        """boots prerequisites and runs the uvicorn asgi listener"""
        try:
            await self.start_prerequisites()
            config = uvicorn.Config(
                app=self.fastapi.app,
                host=self.listener_opts.host,
                port=self.listener_opts.port,
                log_config=None,  # use configured app_logger
            )
            self._uvicorn_server = uvicorn.Server(config)
            app_logger.info(
                "[Server] Listening on http://%s:%d",
                self.listener_opts.host,
                self.listener_opts.port,
            )
            await self._uvicorn_server.serve()
        except Exception as err:
            app_logger.error("[Server] Boot failure: %s", err)
            sys.exit(1)
        finally:
            await self.shutdown()


# export default server and asgi application instance
server = Server()
app = server.fastapi.app

if __name__ == "__main__":
    try:
        asyncio.run(server.start())
    except KeyboardInterrupt:
        pass
