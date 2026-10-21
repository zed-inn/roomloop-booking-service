import os
import sys

from roomloop.config.database import DatabaseConnection
from roomloop.modules.bookings.model import BookingModel, SeriesModel
from roomloop.modules.rooms.model import RoomModel
from roomloop.shared.models import Base, register_models
from roomloop.shared.services.logger import app_logger

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

    def seed_sample_bookings(self) -> None:
        """seeds initial historical and recurring bookings across rooms for load testing"""
        with self.db.get_session() as session:
            # Seed a sample recurring series
            series1 = SeriesModel(
                room_id=3,
                user_name="alex",
                repeat_until="2027-06-30",
                created_at_utc="2026-01-01T00:00:00Z",
            )
            session.add(series1)
            session.flush()

            # Seed recurring occurrences for series1
            for week in range(4):
                day = 5 + week * 7
                booking = BookingModel(
                    room_id=3,
                    series_id=series1.id,
                    user_name="alex",
                    start_local=f"2027-05-{day:02d}T09:00:00",
                    end_local=f"2027-05-{day:02d}T10:00:00",
                    status="active",
                    created_at_utc="2026-01-01T00:00:00Z",
                )
                session.add(booking)

            # Seed standalone bookings for other rooms
            sample_singles = [
                (4, "sam", "2027-05-10T14:00:00", "2027-05-10T15:00:00"),
                (9, "jordan", "2027-05-12T10:00:00", "2027-05-12T11:00:00"),
                (17, "taylor", "2027-05-15T11:00:00", "2027-05-15T12:00:00"),
            ]
            for room_id, user, start, end in sample_singles:
                session.add(
                    BookingModel(
                        room_id=room_id,
                        user_name=user,
                        start_local=start,
                        end_local=end,
                        status="active",
                        created_at_utc="2026-01-01T00:00:00Z",
                    )
                )

            session.commit()
            app_logger.info("[Database Seeder] Sample initial bookings seeded")

    def seed_all(self, rich: bool = False) -> None:
        """executes all seed routines"""
        self.seed_rooms()
        if rich:
            self.seed_sample_bookings()


def run_seed() -> None:
    """standalone cli runner for seeding database"""
    rich = "--rich" in sys.argv or os.getenv("RICH_SEED") == "true"
    db = DatabaseConnection()
    db.connect()
    try:
        register_models()
        Base.metadata.create_all(bind=db.engine)
        seeder = DatabaseSeeder(db)
        seeder.seed_all(rich=rich)
    finally:
        db.disconnect()


if __name__ == "__main__":
    run_seed()
