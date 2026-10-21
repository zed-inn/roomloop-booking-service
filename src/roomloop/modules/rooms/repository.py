from sqlalchemy import select
from sqlalchemy.orm import Session

from roomloop.config.database import DatabaseConnection
from roomloop.modules.rooms.model import RoomModel


class RoomRepository:
    """manages database query and persistence operations for rooms entity"""

    def __init__(self, db: DatabaseConnection) -> None:
        self.db = db

    def list_active(self) -> list[RoomModel]:
        """fetches all active bookable rooms ordered by id"""
        with self.db.get_session() as session:
            stmt = (
                select(RoomModel)
                .where(RoomModel.is_active.is_(True))
                .order_by(RoomModel.id.asc())
            )
            return list(session.scalars(stmt).all())

    def get_by_id(
        self, room_id: int, session: Session | None = None
    ) -> RoomModel | None:
        """fetches room by primary key id if active, optionally reusing an active session"""
        if not isinstance(room_id, int) or room_id <= 0:
            return None
        stmt = select(RoomModel).where(
            RoomModel.id == room_id, RoomModel.is_active.is_(True)
        )
        if session is not None:
            return session.scalars(stmt).first()
        with self.db.get_session() as s:
            return s.scalars(stmt).first()

    def create(self, room: RoomModel) -> RoomModel:
        """persists a new room record"""
        with self.db.get_session() as session:
            session.add(room)
            session.commit()
            session.refresh(room)
            return room
