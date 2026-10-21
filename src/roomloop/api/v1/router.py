from fastapi import APIRouter, FastAPI

from roomloop.config.database import DatabaseConnection
from roomloop.modules.bookings.routes import create_bookings_router
from roomloop.modules.rooms.routes import create_rooms_router
from roomloop.shared.services.logger import app_logger


def register_api_v1_routes(
    app: FastAPI, db: DatabaseConnection | None = None
) -> None:
    """mounts api v1 feature module routers onto the fastapi application with injected database dependency"""
    v1_router = APIRouter(prefix="/api/v1")

    if db is not None:
        rooms_router = create_rooms_router(db)
        v1_router.include_router(rooms_router, prefix="/rooms")
        # also mount directly at /rooms for strict contract c2 compliance
        app.include_router(rooms_router, prefix="/rooms")

        bookings_router = create_bookings_router(db)
        v1_router.include_router(bookings_router, prefix="/bookings")
        # also mount directly at /bookings for top-level rest convenience
        app.include_router(bookings_router, prefix="/bookings")

    app.include_router(v1_router)
    app_logger.info("[Router] API v1 routes registered successfully")
