from roomloop.modules.rooms.contract import RoomResponse
from roomloop.modules.rooms.service import RoomService


class RoomController:
    """handles http endpoint coordination for room resources"""

    def __init__(self, room_service: RoomService) -> None:
        self.room_service = room_service

    async def get_rooms(self) -> list[RoomResponse]:
        """endpoint handler returning active rooms strictly matching contract c2"""
        return self.room_service.get_active_rooms()
