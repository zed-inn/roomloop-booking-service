from concurrent.futures import ThreadPoolExecutor
from fastapi.testclient import TestClient

from roomloop.config.database import DatabaseConnection
from roomloop.modules.bookings.model import BookingModel
from roomloop.seeding.seeder import DatabaseSeeder
from roomloop.server import Server
from roomloop.shared.models.base import Base


def test_concurrent_booking_requests_prevent_race_conditions(tmp_path):
    """verifies that immediate write locking serializes concurrent requests and prevents double bookings"""
    db_path = str(tmp_path / "concurrency_test.db")
    db = DatabaseConnection(db_path=db_path)
    db.connect()
    Base.metadata.create_all(bind=db.engine)
    seeder = DatabaseSeeder(db)
    seeder.seed_all()
    server = Server(database=db)

    slot_payload = {
        "room_id": 3,
        "start": "2026-11-20T14:00:00",
        "end": "2026-11-20T15:00:00",
        "user": "race-tester",
    }

    def attempt_booking(worker_id: int):
        # each thread uses a testclient to dispatch requests
        with TestClient(server.fastapi.app) as client:
            return client.post(
                "/bookings",
                json={**slot_payload, "user": f"worker-{worker_id}"},
            )

    worker_count = 8
    with ThreadPoolExecutor(max_workers=worker_count) as executor:
        responses = list(executor.map(attempt_booking, range(worker_count)))

    status_codes = [r.status_code for r in responses]

    # exactly one request must win with 201 Created
    assert status_codes.count(201) == 1
    # the remaining 7 requests must receive 409 Conflict (or busy lock rejection)
    assert status_codes.count(409) == worker_count - 1

    # verify database state: exactly 1 booking exists in the table
    with db.get_session() as session:
        from sqlalchemy import select

        stmt = select(BookingModel).where(
            BookingModel.room_id == 3,
            BookingModel.start_local == "2026-11-20T14:00:00",
            BookingModel.status == "active",
        )
        active_bookings = list(session.scalars(stmt).all())
        assert len(active_bookings) == 1

    db.disconnect()
