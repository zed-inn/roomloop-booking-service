from fastapi.testclient import TestClient
import pytest

from roomloop.config.database import DatabaseConnection
from roomloop.seeding.seeder import DatabaseSeeder
from roomloop.server import Server
from roomloop.shared.models.base import Base


@pytest.fixture
def booking_client(tmp_path):
    """creates test database and fastapi testclient fixture"""
    db_path = str(tmp_path / "bookings_test.db")
    db = DatabaseConnection(db_path=db_path)
    db.connect()
    Base.metadata.create_all(bind=db.engine)
    seeder = DatabaseSeeder(db)
    seeder.seed_all()
    server = Server(database=db)
    with TestClient(server.fastapi.app) as client:
        yield client, db
    db.disconnect()


def test_create_single_booking_happy_path(booking_client):
    """verifies single booking creation returns 201 with matching contract c1 timestamp format"""
    client, _ = booking_client
    payload = {
        "room_id": 3,
        "start": "2026-11-10T09:00:00",
        "end": "2026-11-10T10:00:00",
        "user": "kartikey",
    }
    res = client.post("/bookings", json=payload)
    assert res.status_code == 201
    data = res.json()
    assert data["room_id"] == 3
    assert data["series_id"] is None
    assert data["user"] == "kartikey"
    assert data["start"] == "2026-11-10T09:00:00"
    assert data["end"] == "2026-11-10T10:00:00"
    assert data["status"] == "active"
    assert "created_at_utc" in data


def test_create_single_booking_conflict_rejection(booking_client):
    """verifies overlapping booking in same room returns 409 conflict"""
    client, _ = booking_client
    payload_1 = {
        "room_id": 3,
        "start": "2026-11-10T09:00:00",
        "end": "2026-11-10T10:00:00",
        "user": "alice",
    }
    res_1 = client.post("/bookings", json=payload_1)
    assert res_1.status_code == 201

    # overlapping slot: 09:30 - 10:30
    payload_overlap = {
        "room_id": 3,
        "start": "2026-11-10T09:30:00",
        "end": "2026-11-10T10:30:00",
        "user": "bob",
    }
    res_overlap = client.post("/bookings", json=payload_overlap)
    assert res_overlap.status_code == 409
    assert "Conflict detected" in res_overlap.json()["detail"]


def test_back_to_back_bookings_succeed(booking_client):
    """verifies that back-to-back half-open intervals [09:00, 10:00) and [10:00, 11:00) do not conflict"""
    client, _ = booking_client
    first = client.post(
        "/bookings",
        json={
            "room_id": 3,
            "start": "2026-11-10T09:00:00",
            "end": "2026-11-10T10:00:00",
            "user": "alice",
        },
    )
    assert first.status_code == 201

    second = client.post(
        "/bookings",
        json={
            "room_id": 3,
            "start": "2026-11-10T10:00:00",
            "end": "2026-11-10T11:00:00",
            "user": "bob",
        },
    )
    assert second.status_code == 201


def test_single_booking_non_existent_room_returns_404(booking_client):
    """verifies requesting non-existent room returns 404 not found"""
    client, _ = booking_client
    res = client.post(
        "/bookings",
        json={
            "room_id": 999,
            "start": "2026-11-10T09:00:00",
            "end": "2026-11-10T10:00:00",
            "user": "charlie",
        },
    )
    assert res.status_code == 404


def test_single_booking_dst_gap_rejected(booking_client):
    """verifies that booking scheduled at non-existent spring-forward local time returns 422"""
    client, _ = booking_client
    # berlin spring-forward gap on 2027-03-28 02:30:00
    res = client.post(
        "/bookings",
        json={
            "room_id": 3,  # berlin HQ room
            "start": "2027-03-28T02:30:00",
            "end": "2027-03-28T03:30:00",
            "user": "david",
        },
    )
    assert res.status_code == 422


def test_recurring_booking_happy_path(booking_client):
    """verifies recurring booking creation upfront across 4 weeks with zero conflicts"""
    client, _ = booking_client
    payload = {
        "room_id": 4,  # berlin kreuzberg
        "start": "2026-11-04T14:00:00",
        "end": "2026-11-04T15:00:00",
        "user": "engineering-team",
        "repeat_until": "2026-11-25",
    }
    res = client.post("/bookings/recurring", json=payload)
    assert res.status_code == 201
    data = res.json()
    assert data["total_requested"] == 4
    assert data["created_count"] == 4
    assert data["skipped_count"] == 0
    assert len(data["created"]) == 4
    assert len(data["skipped"]) == 0
    assert data["series_id"] >= 1


def test_recurring_booking_r2_skips_up_to_two_conflicts(booking_client):
    """verifies r2 exception: 4-week series with 2 pre-existing clashes skips them and creates remaining 2 (50%)"""
    client, _ = booking_client
    # pre-book week 1 (2026-11-04) and week 3 (2026-11-18)
    client.post(
        "/bookings",
        json={
            "room_id": 4,
            "start": "2026-11-04T14:00:00",
            "end": "2026-11-04T15:00:00",
            "user": "existing-1",
        },
    )
    client.post(
        "/bookings",
        json={
            "room_id": 4,
            "start": "2026-11-18T14:00:00",
            "end": "2026-11-18T15:00:00",
            "user": "existing-2",
        },
    )

    # request 4-week series (Nov 4, 11, 18, 25)
    res = client.post(
        "/bookings/recurring",
        json={
            "room_id": 4,
            "start": "2026-11-04T14:00:00",
            "end": "2026-11-04T15:00:00",
            "user": "recurring-booker",
            "repeat_until": "2026-11-25",
        },
    )
    assert res.status_code == 201
    data = res.json()
    assert data["total_requested"] == 4
    assert data["created_count"] == 2
    assert data["skipped_count"] == 2
    assert len(data["skipped"]) == 2
    skipped_starts = [item["start"] for item in data["skipped"]]
    assert "2026-11-04T14:00:00" in skipped_starts
    assert "2026-11-18T14:00:00" in skipped_starts


def test_recurring_booking_r1_rollback_when_zero_slots_created(booking_client):
    """verifies r1 all-or-nothing rollback when 2-instance series has 2 conflicts (0% created)"""
    client, _ = booking_client
    # pre-book week 1 and week 2
    client.post(
        "/bookings",
        json={
            "room_id": 4,
            "start": "2026-11-04T10:00:00",
            "end": "2026-11-04T11:00:00",
            "user": "blocker-1",
        },
    )
    client.post(
        "/bookings",
        json={
            "room_id": 4,
            "start": "2026-11-11T10:00:00",
            "end": "2026-11-11T11:00:00",
            "user": "blocker-2",
        },
    )

    # request 2-week series: both conflict
    res = client.post(
        "/bookings/recurring",
        json={
            "room_id": 4,
            "start": "2026-11-04T10:00:00",
            "end": "2026-11-04T11:00:00",
            "user": "unlucky",
            "repeat_until": "2026-11-11",
        },
    )
    assert res.status_code == 409
    assert "conflicts exceed threshold" in res.json()["detail"]


def test_recurring_booking_r1_rollback_when_exceeding_two_conflicts(
    booking_client,
):
    """verifies r1 all-or-nothing rollback when conflicts exceed 2, even if total created >= 50%"""
    client, _ = booking_client
    # pre-book 3 dates: Nov 4, Nov 11, Nov 18
    for d in ["2026-11-04", "2026-11-11", "2026-11-18"]:
        client.post(
            "/bookings",
            json={
                "room_id": 9,  # denver lodo
                "start": f"{d}T10:00:00",
                "end": f"{d}T11:00:00",
                "user": "blocker",
            },
        )

    # request 10-week series (Nov 4 to Jan 6) -> 3 conflicts exceeds max 2
    res = client.post(
        "/bookings/recurring",
        json={
            "room_id": 9,
            "start": "2026-11-04T10:00:00",
            "end": "2026-11-04T11:00:00",
            "user": "long-series",
            "repeat_until": "2027-01-06",
        },
    )
    assert res.status_code == 409
    assert "3 conflicts exceed threshold" in res.json()["detail"]
