from roomloop.config.database import DatabaseConnection
from roomloop.modules.rooms.model import RoomModel
from roomloop.shared.models.base import Base
from roomloop.shared.services.logger import app_logger

# prototype rooms strictly matching take-home contract c2 and multi-office requirements
PROTOTYPE_ROOMS: list[dict[str, object]] = [
    {"id": 3, "name": "Neukölln", "capacity": 8, "timezone": "Europe/Berlin"},
    {"id": 4, "name": "Kreuzberg", "capacity": 12, "timezone": "Europe/Berlin"},
    {"id": 9, "name": "LoDo", "capacity": 6, "timezone": "America/Denver"},
    {"id": 17, "name": "RiNo", "capacity": 16, "timezone": "America/Denver"},
]


class DatabaseSeeder:
    """orchestrates database seeding across all domain datasets outside feature modules"""

    def __init__(self, db: DatabaseConnection) -> None:
        self.db = db

    def seed_rooms(self) -> None:
        """idempotently seeds prototype rooms if not already existing"""
        with self.db.get_session() as session:
            for item in PROTOTYPE_ROOMS:
                existing = session.get(RoomModel, int(item["id"]))
                if existing is None:
                    room = RoomModel(
                        id=int(item["id"]),
                        name=str(item["name"]),
                        capacity=int(item["capacity"]),
                        timezone=str(item["timezone"]),
                        is_active=True,
                    )
                    session.add(room)
            session.commit()
            app_logger.info("[Database Seeder] Prototype rooms verified and seeded")

    def seed_all(self) -> None:
        """executes all seed routines"""
        self.seed_rooms()


def run_seed() -> None:
    """standalone cli runner for seeding database"""
    db = DatabaseConnection()
    db.connect()
    try:
        # ensure tables exist before seeding
        Base.metadata.create_all(bind=db.engine)
        seeder = DatabaseSeeder(db)
        seeder.seed_all()
    finally:
        db.disconnect()


if __name__ == "__main__":
    run_seed()

