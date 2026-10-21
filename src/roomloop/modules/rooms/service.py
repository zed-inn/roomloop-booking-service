from roomloop.modules.rooms.contract import RoomResponse
from roomloop.modules.rooms.model import RoomModel
from roomloop.modules.rooms.repository import RoomRepository


class RoomService:
    """business logic service for room management and contract transformation"""

    def __init__(self, room_repo: RoomRepository) -> None:
        self.room_repo = room_repo

    def get_active_rooms(self) -> list[RoomResponse]:
        """retrieves all active rooms mapped to contract c2 response dtos"""
        room_entities = self.room_repo.list_active()
        return [
            RoomResponse(
                id=room.id,
                name=room.name,
                capacity=room.capacity,
            )
            for room in room_entities
        ]

    def get_room_by_id(self, room_id: int) -> RoomModel | None:
        """retrieves active room entity by id"""
        return self.room_repo.get_by_id(room_id)
