from sqlalchemy import select
from sqlalchemy.orm import Session

from roomloop.config.database import DatabaseConnection
from roomloop.modules.rooms.model import RoomModel


class RoomRepository:
    """manages database query and persistence operations for rooms entity with in-memory caching"""

    def __init__(self, db: DatabaseConnection) -> None:
        self.db = db
        self._cache: dict[int, RoomModel] = {}

    def list_active(self) -> list[RoomModel]:
        """fetches all active bookable rooms ordered by id, reusing cached instances when populated"""
        if self._cache and len(self._cache) >= 4:
            return sorted(self._cache.values(), key=lambda r: r.id)
        with self.db.get_session() as session:
            stmt = (
                select(RoomModel)
                .where(RoomModel.is_active.is_(True))
                .order_by(RoomModel.id.asc())
            )
            rooms = list(session.scalars(stmt).all())
            for r in rooms:
                session.expunge(r)
                self._cache[r.id] = r
            return rooms

    def get_by_id(
        self, room_id: int, session: Session | None = None
    ) -> RoomModel | None:
        """fetches room by primary key id if active, optionally reusing an active session or cache"""
        if not isinstance(room_id, int) or room_id <= 0:
            return None
        if session is None and room_id in self._cache:
            return self._cache[room_id]

        stmt = select(RoomModel).where(
            RoomModel.id == room_id, RoomModel.is_active.is_(True)
        )
        if session is not None:
            return session.scalars(stmt).first()
        with self.db.get_session() as s:
            room = s.scalars(stmt).first()
            if room is not None:
                s.expunge(room)
                self._cache[room_id] = room
            return room

    def create(self, room: RoomModel) -> RoomModel:
        """persists a new room record and updates the in-memory cache"""
        with self.db.get_session() as session:
            session.add(room)
            session.commit()
            session.refresh(room)
            session.expunge(room)
            self._cache[room.id] = room
            return room
