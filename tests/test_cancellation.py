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
        "/api/v1/bookings",
        json={
            "room_id": 3,
            "start": "2026-11-15T09:00:00",
            "end": "2026-11-15T10:00:00",
            "user": "alice",
        },
    )
    assert create_res.status_code == 201
    booking_id = create_res.json()["id"]

    cancel_res = client.delete(f"/api/v1/bookings/{booking_id}")
    assert cancel_res.status_code == 200
    cancel_data = cancel_res.json()
    assert cancel_data["id"] == booking_id
    assert cancel_data["status"] == "cancelled"
    assert "cancelled_at_utc" in cancel_data

    rebook_res = client.post(
        "/api/v1/bookings",
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
    res = client.delete("/api/v1/bookings/999999")
    assert res.status_code == 404


def test_cancel_series_future_instances_resolves_om1(cancel_client):
    """verifies office manager om-1: whole series can be easily cancelled freeing all future slots"""
    client, _ = cancel_client
    series_res = client.post(
        "/api/v1/bookings/recurring",
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

    del_res = client.delete(f"/api/v1/bookings/series/{series_id}")
    assert del_res.status_code == 200
    del_data = del_res.json()
    assert del_data["series_id"] == series_id
    assert del_data["cancelled_count"] == 4
    assert del_data["kept_count"] == 0

    new_res = client.post(
        "/api/v1/bookings",
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

    res = client.delete(f"/api/v1/bookings/series/{series_id}")
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
        "/api/v1/bookings",
        json={
            "room_id": 4,
            "start": "2026-11-16T11:00:00",
            "end": "2026-11-16T12:00:00",
            "user": "audit-cancel",
        },
    )
    b_id = b_res.json()["id"]
    client.delete(f"/api/v1/bookings/{b_id}")

    s_res = client.post(
        "/api/v1/bookings/recurring",
        json={
            "room_id": 4,
            "start": "2026-11-17T11:00:00",
            "end": "2026-11-17T12:00:00",
            "user": "audit-cancel-series",
            "repeat_until": "2026-11-24",
        },
    )
    s_id = s_res.json()["series_id"]
    client.delete(f"/api/v1/bookings/series/{s_id}")

    repo = AuditLogRepository(db)
    logs = repo.list_events()
    event_types = [l.event_type for l in logs]
    assert "BOOKING_CANCELLED" in event_types
    assert "SERIES_CANCELLED" in event_types


def test_unversioned_routes_rejected(cancel_client):
    """verifies that unversioned booking routes return 404, with only get /rooms unversioned"""
    client, _ = cancel_client
    assert client.delete("/series/1").status_code == 404
    assert client.post("/bookings", json={}).status_code == 404
    assert client.delete("/bookings/1").status_code == 404
    assert client.get("/rooms").status_code == 200


def test_cancel_series_individual_instance_rejected(cancel_client):
    """verifies that attempting to cancel an individual occurrence of a series returns 400"""
    client, db = cancel_client
    series_res = client.post(
        "/api/v1/bookings/recurring",
        json={
            "room_id": 9,
            "start": "2026-11-20T10:00:00",
            "end": "2026-11-20T11:00:00",
            "user": "whole-series-user",
            "repeat_until": "2026-12-04",
        },
    )
    assert series_res.status_code == 201
    series_data = series_res.json()
    series_id = series_data["series_id"]
    first_instance_id = series_data["created"][0]["id"]

    # attempting to cancel single instance of series is rejected
    del_res = client.delete(f"/api/v1/bookings/{first_instance_id}")
    assert del_res.status_code == 400
    assert "belongs to recurring series" in del_res.json()["detail"]
    assert (
        "Individual series instances cannot be cancelled separately"
        in del_res.json()["detail"]
    )

    # instance remains active
    with db.get_session() as session:
        booking = session.get(BookingModel, first_instance_id)
        assert booking is not None
        assert booking.status == "active"

    # cancelling series properly cancels future instances
    series_cancel_res = client.delete(f"/api/v1/bookings/series/{series_id}")
    assert series_cancel_res.status_code == 200
    assert series_cancel_res.json()["cancelled_count"] == 3


def test_double_cancellation_single_booking_is_idempotent(cancel_client):
    """verifies cancelling an already cancelled single booking returns 200 and preserves original timestamp"""
    client, _ = cancel_client
    b = client.post(
        "/api/v1/bookings",
        json={
            "room_id": 3,
            "start": "2026-11-20T14:00:00",
            "end": "2026-11-20T15:00:00",
            "user": "idempotent-tester",
        },
    ).json()

    first_cancel = client.delete(f"/api/v1/bookings/{b['id']}")
    assert first_cancel.status_code == 200
    ts_1 = first_cancel.json()["cancelled_at_utc"]

    second_cancel = client.delete(f"/api/v1/bookings/{b['id']}")
    assert second_cancel.status_code == 200
    assert second_cancel.json()["status"] == "cancelled"
    assert second_cancel.json()["cancelled_at_utc"] == ts_1


def test_cancel_series_double_cancellation_is_idempotent(cancel_client):
    """verifies calling delete on already cancelled series returns 200 with cancelled_count=0"""
    client, _ = cancel_client
    s = client.post(
        "/api/v1/bookings/recurring",
        json={
            "room_id": 9,
            "start": "2026-11-25T10:00:00",
            "end": "2026-11-25T11:00:00",
            "user": "double-cancel-series",
            "repeat_until": "2026-12-02",
        },
    ).json()

    first = client.delete(f"/api/v1/bookings/series/{s['series_id']}")
    assert first.status_code == 200
    assert first.json()["cancelled_count"] == 2

    second = client.delete(f"/api/v1/bookings/series/{s['series_id']}")
    assert second.status_code == 200
    assert second.json()["cancelled_count"] == 0


def test_cancel_series_not_found_returns_404(cancel_client):
    """verifies cancelling non-existent series returns 404"""
    client, _ = cancel_client
    res = client.delete("/api/v1/bookings/series/88888")
    assert res.status_code == 404


def test_cancel_series_all_past_instances_leaves_zero_cancelled(cancel_client):
    """verifies series with only past instances results in cancelled_count=0 and kept_count=N"""
    client, db = cancel_client
    with db.get_session() as session:
        series = SeriesModel(
            room_id=4,
            user_name="ancient-team",
            repeat_until="2026-05-30",
            created_at_utc="2026-05-01T00:00:00Z",
        )
        session.add(series)
        session.flush()

        b1 = BookingModel(
            room_id=4,
            series_id=series.id,
            user_name="ancient-team",
            start_local="2026-05-10T10:00:00",
            end_local="2026-05-10T11:00:00",
            status="active",
            created_at_utc="2026-05-01T00:00:00Z",
        )
        b2 = BookingModel(
            room_id=4,
            series_id=series.id,
            user_name="ancient-team",
            start_local="2026-05-17T10:00:00",
            end_local="2026-05-17T11:00:00",
            status="active",
            created_at_utc="2026-05-01T00:00:00Z",
        )
        session.add(b1)
        session.add(b2)
        session.commit()
        s_id = series.id

    res = client.delete(f"/api/v1/bookings/series/{s_id}")
    assert res.status_code == 200
    assert res.json()["cancelled_count"] == 0
    assert res.json()["kept_count"] == 2
