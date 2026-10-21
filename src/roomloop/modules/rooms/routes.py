from fastapi import APIRouter

from roomloop.config.database import DatabaseConnection
from roomloop.modules.rooms.contract import RoomResponse
from roomloop.modules.rooms.controller import RoomController
from roomloop.modules.rooms.repository import RoomRepository
from roomloop.modules.rooms.service import RoomService


def create_rooms_router(db: DatabaseConnection) -> APIRouter:
    """creates and configures rooms api router with injected database connection"""
    room_repo = RoomRepository(db)
    room_service = RoomService(room_repo)
    controller = RoomController(room_service)

    router = APIRouter(tags=["rooms"])

    @router.get("", response_model=list[RoomResponse])
    async def get_rooms() -> list[RoomResponse]:
        return await controller.get_rooms()

    return router
