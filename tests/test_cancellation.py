import pytest
from fastapi.testclient import TestClient

from roomloop.config.database import DatabaseConnection
from roomloop.modules.audit.repository import AuditLogRepository
from roomloop.modules.bookings.model import BookingModel, SeriesModel
from roomloop.seeding.seeder import DatabaseSeeder
from roomloop.server import Server
from roomloop.shared.models.base import Base


@pytest.fixture
def cancel_client(tmp_path):
    """creates test database and fastapi testclient fixture for cancellation testing"""
    db_path = str(tmp_path / "cancellation_test.db")
    db = DatabaseConnection(db_path=db_path)
    db.connect()
    Base.metadata.create_all(bind=db.engine)
    seeder = DatabaseSeeder(db)
    seeder.seed_all()
    server = Server(database=db)
    with TestClient(server.fastapi.app) as client:
        yield client, db
    db.disconnect()


def test_cancel_single_booking_success(cancel_client):
    """verifies single booking cancellation updates status to cancelled and frees slot"""
    client, _ = cancel_client
    create_res = client.post(
        "/bookings",
        json={
            "room_id": 3,
            "start": "2026-11-15T09:00:00",
            "end": "2026-11-15T10:00:00",
            "user": "alice",
        },
    )
    assert create_res.status_code == 201
    booking_id = create_res.json()["id"]

    cancel_res = client.delete(f"/bookings/{booking_id}")
    assert cancel_res.status_code == 200
    cancel_data = cancel_res.json()
    assert cancel_data["id"] == booking_id
    assert cancel_data["status"] == "cancelled"
    assert "cancelled_at_utc" in cancel_data

    rebook_res = client.post(
        "/bookings",
        json={
            "room_id": 3,
            "start": "2026-11-15T09:00:00",
            "end": "2026-11-15T10:00:00",
            "user": "bob",
        },
    )
    assert rebook_res.status_code == 201
    assert rebook_res.json()["user"] == "bob"


def test_cancel_single_booking_not_found(cancel_client):
    """verifies cancelling non-existent booking returns 404"""
    client, _ = cancel_client
    res = client.delete("/bookings/999999")
    assert res.status_code == 404


def test_cancel_series_future_instances_resolves_om1(cancel_client):
    """verifies office manager om-1: whole series can be easily cancelled freeing all future slots"""
    client, _ = cancel_client
    series_res = client.post(
        "/bookings/recurring",
        json={
            "room_id": 9,
            "start": "2026-11-10T14:00:00",
            "end": "2026-11-10T15:00:00",
            "user": "dissolved-team",
            "repeat_until": "2026-12-01",
        },
    )
    assert series_res.status_code == 201
    series_id = series_res.json()["series_id"]

    del_res = client.delete(f"/series/{series_id}")
    assert del_res.status_code == 200
    del_data = del_res.json()
    assert del_data["series_id"] == series_id
    assert del_data["cancelled_count"] == 4
    assert del_data["kept_count"] == 0

    new_res = client.post(
        "/bookings",
        json={
            "room_id": 9,
            "start": "2026-11-10T14:00:00",
            "end": "2026-11-10T15:00:00",
            "user": "new-team",
        },
    )
    assert new_res.status_code == 201


def test_cancel_series_preserves_past_instances(cancel_client):
    """verifies cancelling recurring booking cancels future instances but leaves past ones intact"""
    client, db = cancel_client

    with db.get_session() as session:
        series = SeriesModel(
            room_id=3,
            user_name="historical-team",
            repeat_until="2026-11-20",
            created_at_utc="2026-08-01T00:00:00Z",
        )
        session.add(series)
        session.flush()

        past_booking = BookingModel(
            room_id=3,
            series_id=series.id,
            user_name="historical-team",
            start_local="2026-08-10T09:00:00",
            end_local="2026-08-10T10:00:00",
            status="active",
            created_at_utc="2026-08-01T00:00:00Z",
        )
        future_booking = BookingModel(
            room_id=3,
            series_id=series.id,
            user_name="historical-team",
            start_local="2026-11-10T09:00:00",
            end_local="2026-11-10T10:00:00",
            status="active",
            created_at_utc="2026-08-01T00:00:00Z",
        )
        session.add(past_booking)
        session.add(future_booking)
        session.commit()
        series_id = series.id
        past_id = past_booking.id
        future_id = future_booking.id

    res = client.delete(f"/series/{series_id}")
    assert res.status_code == 200
    data = res.json()
    assert data["cancelled_count"] == 1
    assert data["kept_count"] == 1

    with db.get_session() as session:
        past_b = session.get(BookingModel, past_id)
        future_b = session.get(BookingModel, future_id)
        assert past_b is not None
        assert past_b.status == "active"
        assert future_b is not None
        assert future_b.status == "cancelled"


def test_cancel_audit_logging(cancel_client):
    """verifies that booking and series cancellations append records to audit_logs"""
    client, db = cancel_client

    b_res = client.post(
        "/bookings",
        json={
            "room_id": 4,
            "start": "2026-11-16T11:00:00",
            "end": "2026-11-16T12:00:00",
            "user": "audit-cancel",
        },
    )
    b_id = b_res.json()["id"]
    client.delete(f"/bookings/{b_id}")

    s_res = client.post(
        "/bookings/recurring",
        json={
            "room_id": 4,
            "start": "2026-11-17T11:00:00",
            "end": "2026-11-17T12:00:00",
            "user": "audit-cancel-series",
            "repeat_until": "2026-11-24",
        },
    )
    s_id = s_res.json()["series_id"]
    client.delete(f"/series/{s_id}")

    repo = AuditLogRepository(db)
    logs = repo.list_events()
    event_types = [l.event_type for l in logs]
    assert "BOOKING_CANCELLED" in event_types
    assert "SERIES_CANCELLED" in event_types
