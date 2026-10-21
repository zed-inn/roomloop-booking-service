import json

import pytest
from fastapi.testclient import TestClient

from roomloop.config.database import DatabaseConnection
from roomloop.modules.audit.repository import AuditLogRepository
from roomloop.seeding.seeder import DatabaseSeeder
from roomloop.server import Server
from roomloop.shared.models.base import Base


@pytest.fixture
def audit_test_setup(tmp_path):
    """creates test database and fastapi testclient fixture for audit testing"""
    db_path = str(tmp_path / "audit_test.db")
    db = DatabaseConnection(db_path=db_path)
    db.connect()
    Base.metadata.create_all(bind=db.engine)
    seeder = DatabaseSeeder(db)
    seeder.seed_all()
    server = Server(database=db)
    with TestClient(server.fastapi.app) as client:
        yield client, db
    db.disconnect()


def test_audit_logs_record_single_booking(audit_test_setup):
    """verifies that creating a single booking writes an immutable record to audit_logs table"""
    client, db = audit_test_setup
    payload = {
        "room_id": 3,
        "start": "2026-11-12T10:00:00",
        "end": "2026-11-12T11:00:00",
        "user": "audit-tester",
    }
    res = client.post("/bookings", json=payload)
    assert res.status_code == 201

    repo = AuditLogRepository(db)
    logs = repo.list_events()
    assert len(logs) >= 1

    booking_event = next(
        (log for log in logs if log.event_type == "BOOKING_CREATED"), None
    )
    assert booking_event is not None
    assert booking_event.entity_type == "booking"
    assert booking_event.user_name == "audit-tester"
    details = json.loads(booking_event.details_json)
    assert details["room_id"] == 3
    assert details["start"] == "2026-11-12T10:00:00"
    assert details["end"] == "2026-11-12T11:00:00"


def test_audit_logs_record_series_creation_and_rollback(audit_test_setup):
    """verifies that series creation and series rollback events are persisted in audit_logs"""
    client, db = audit_test_setup

    client.post(
        "/bookings/recurring",
        json={
            "room_id": 9,
            "start": "2026-11-05T09:00:00",
            "end": "2026-11-05T10:00:00",
            "user": "series-user",
            "repeat_until": "2026-11-19",
        },
    )

    client.post(
        "/bookings/recurring",
        json={
            "room_id": 9,
            "start": "2026-11-05T09:00:00",
            "end": "2026-11-05T10:00:00",
            "user": "conflict-user",
            "repeat_until": "2026-11-19",
        },
    )

    client.post(
        "/bookings",
        json={
            "room_id": 4,
            "start": "2026-11-26T14:00:00",
            "end": "2026-11-26T15:00:00",
            "user": "single-blocker",
        },
    )
    client.post(
        "/bookings/recurring",
        json={
            "room_id": 4,
            "start": "2026-11-26T14:00:00",
            "end": "2026-11-26T15:00:00",
            "user": "skip-user",
            "repeat_until": "2026-12-17",
        },
    )

    repo = AuditLogRepository(db)
    logs = repo.list_events()
    event_types = [l.event_type for l in logs]
    assert "SERIES_CREATED" in event_types
    assert "SERIES_ROLLED_BACK" in event_types
    assert "CONFLICT_SKIPPED" in event_types
