from fastapi import APIRouter, FastAPI

from roomloop.config.database import DatabaseConnection
from roomloop.shared.services.logger import app_logger

api_v1_router = APIRouter(prefix="/api/v1")


def register_api_v1_routes(app: FastAPI, db: DatabaseConnection | None = None) -> None:
    """mounts api v1 feature module routers onto the fastapi application with injected database dependency"""
    # feature module routers (rooms, bookings, audit) will be registered here with db injected
    app.include_router(api_v1_router)
    app_logger.info("[Router] API v1 routes registered successfully")
