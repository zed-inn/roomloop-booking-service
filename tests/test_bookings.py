import pytest
from fastapi.testclient import TestClient

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
        "user": "alex",
    }
    res = client.post("/api/v1/bookings", json=payload)
    assert res.status_code == 201
    data = res.json()
    assert data["room_id"] == 3
    assert data["series_id"] is None
    assert data["user"] == "alex"
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
    res_1 = client.post("/api/v1/bookings", json=payload_1)
    assert res_1.status_code == 201

    payload_overlap = {
        "room_id": 3,
        "start": "2026-11-10T09:30:00",
        "end": "2026-11-10T10:30:00",
        "user": "bob",
    }
    res_overlap = client.post("/api/v1/bookings", json=payload_overlap)
    assert res_overlap.status_code == 409
    assert "Conflict detected" in res_overlap.json()["detail"]


def test_back_to_back_bookings_succeed(booking_client):
    """verifies that back-to-back half-open intervals [09:00, 10:00) and [10:00, 11:00) do not conflict"""
    client, _ = booking_client
    first = client.post(
        "/api/v1/bookings",
        json={
            "room_id": 3,
            "start": "2026-11-10T09:00:00",
            "end": "2026-11-10T10:00:00",
            "user": "alice",
        },
    )
    assert first.status_code == 201

    second = client.post(
        "/api/v1/bookings",
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
        "/api/v1/bookings",
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
    res = client.post(
        "/api/v1/bookings",
        json={
            "room_id": 3,
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
        "room_id": 4,
        "start": "2026-11-04T14:00:00",
        "end": "2026-11-04T15:00:00",
        "user": "engineering-team",
        "repeat_until": "2026-11-25",
    }
    res = client.post("/api/v1/bookings/recurring", json=payload)
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
    client.post(
        "/api/v1/bookings",
        json={
            "room_id": 4,
            "start": "2026-11-04T14:00:00",
            "end": "2026-11-04T15:00:00",
            "user": "existing-1",
        },
    )
    client.post(
        "/api/v1/bookings",
        json={
            "room_id": 4,
            "start": "2026-11-18T14:00:00",
            "end": "2026-11-18T15:00:00",
            "user": "existing-2",
        },
    )

    res = client.post(
        "/api/v1/bookings/recurring",
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
    client.post(
        "/api/v1/bookings",
        json={
            "room_id": 4,
            "start": "2026-11-04T10:00:00",
            "end": "2026-11-04T11:00:00",
            "user": "blocker-1",
        },
    )
    client.post(
        "/api/v1/bookings",
        json={
            "room_id": 4,
            "start": "2026-11-11T10:00:00",
            "end": "2026-11-11T11:00:00",
            "user": "blocker-2",
        },
    )

    res = client.post(
        "/api/v1/bookings/recurring",
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
    for d in ["2026-11-04", "2026-11-11", "2026-11-18"]:
        client.post(
            "/api/v1/bookings",
            json={
                "room_id": 9,
                "start": f"{d}T10:00:00",
                "end": f"{d}T11:00:00",
                "user": "blocker",
            },
        )

    res = client.post(
        "/api/v1/bookings/recurring",
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


def test_single_booking_multiday_under_7_days_succeeds(booking_client):
    """verifies single booking lasting multiple days (under 7 days) succeeds with 201"""
    client, _ = booking_client
    res = client.post(
        "/api/v1/bookings",
        json={
            "room_id": 9,
            "start": "2026-11-05T00:00:00",
            "end": "2026-11-07T00:00:00",
            "user": "workshop-team",
        },
    )
    assert res.status_code == 201
    assert res.json()["start"] == "2026-11-05T00:00:00"
    assert res.json()["end"] == "2026-11-07T00:00:00"


def test_single_booking_exceeding_7_days_rejected(booking_client):
    """verifies single booking duration exceeding 7 days is rejected with 422"""
    client, _ = booking_client
    res = client.post(
        "/api/v1/bookings",
        json={
            "room_id": 9,
            "start": "2026-11-05T00:00:00",
            "end": "2026-11-13T00:00:00",
            "user": "too-long",
        },
    )
    assert res.status_code == 422
    assert "single meeting duration must be less than 7 days" in res.json()["detail"]


def test_recurring_booking_multi_day_and_invalid_repeat_until_rejected(booking_client):
    """verifies multi-day recurring booking with repeat_until < end is rejected with 422"""
    client, _ = booking_client
    payload = {
        "room_id": 9,
        "start": "2026-11-05T00:00:00",
        "end": "2026-11-07T00:00:00",
        "user": "user2",
        "repeat_until": "2026-11-06T00:00:00",
    }
    res = client.post("/api/v1/bookings/recurring", json=payload)
    assert res.status_code == 422
    assert (
        "repeat_until date cannot be earlier than meeting end date"
        in res.json()["detail"]
    )


def test_recurring_booking_multiday_succeeds_when_repeat_until_valid(booking_client):
    """verifies multi-day recurring booking succeeds when repeat_until >= end_dt.date()"""
    client, _ = booking_client
    payload = {
        "room_id": 9,
        "start": "2026-11-05T00:00:00",
        "end": "2026-11-07T00:00:00",
        "user": "hackathon-series",
        "repeat_until": "2026-11-14",
    }
    res = client.post("/api/v1/bookings/recurring", json=payload)
    assert res.status_code == 201
    data = res.json()
    assert len(data["created"]) == 2
    assert data["created"][0]["start"] == "2026-11-05T00:00:00"
    assert data["created"][0]["end"] == "2026-11-07T00:00:00"
    assert data["created"][1]["start"] == "2026-11-12T00:00:00"
    assert data["created"][1]["end"] == "2026-11-14T00:00:00"


def test_recurring_booking_repeat_until_earlier_than_end_date_rejected(booking_client):
    """verifies recurring booking where repeat_until is before the first instance end date is rejected with 422"""
    client, _ = booking_client
    payload = {
        "room_id": 9,
        "start": "2026-11-05T23:00:00",
        "end": "2026-11-06T01:00:00",
        "user": "late-shift",
        "repeat_until": "2026-11-05",
    }
    res = client.post("/api/v1/bookings/recurring", json=payload)
    assert res.status_code == 422
    assert (
        "repeat_until date cannot be earlier than meeting end date"
        in res.json()["detail"]
    )


def test_unversioned_bookings_routes_return_404(booking_client):
    """verifies that unversioned /bookings routes return 404, while /rooms and /api/v1 routes work"""
    client, _ = booking_client
    assert client.post("/bookings", json={}).status_code == 404
    assert client.post("/bookings/recurring", json={}).status_code == 404
    assert client.delete("/bookings/1").status_code == 404
    assert client.delete("/bookings/series/1").status_code == 404
    assert client.get("/rooms").status_code == 200
    assert client.get("/api/v1/rooms").status_code == 200


def test_single_booking_payload_extra_fields_forbidden(booking_client):
    """verifies that single booking request forbids extraneous fields with 422"""
    client, _ = booking_client
    res = client.post(
        "/api/v1/bookings",
        json={
            "room_id": 3,
            "start": "2026-11-10T09:00:00",
            "end": "2026-11-10T10:00:00",
            "user": "alice",
            "extra_field": "forbidden",
        },
    )
    assert res.status_code == 422


def test_recurring_booking_payload_extra_fields_forbidden(booking_client):
    """verifies that recurring booking request forbids extraneous fields with 422"""
    client, _ = booking_client
    res = client.post(
        "/api/v1/bookings/recurring",
        json={
            "room_id": 3,
            "start": "2026-11-10T09:00:00",
            "end": "2026-11-10T10:00:00",
            "user": "alice",
            "repeat_until": "2026-11-24",
            "notes": "not allowed",
        },
    )
    assert res.status_code == 422


def test_single_booking_empty_user_or_whitespace_rejected(booking_client):
    """verifies that single booking with empty user string is rejected with 422"""
    client, _ = booking_client
    res_empty = client.post(
        "/api/v1/bookings",
        json={
            "room_id": 3,
            "start": "2026-11-10T09:00:00",
            "end": "2026-11-10T10:00:00",
            "user": "",
        },
    )
    assert res_empty.status_code == 422


def test_single_booking_room_id_ge_1_enforced(booking_client):
    """verifies that room_id < 1 is rejected with 422 validation error"""
    client, _ = booking_client
    for invalid_id in [0, -1, -99]:
        res = client.post(
            "/api/v1/bookings",
            json={
                "room_id": invalid_id,
                "start": "2026-11-10T09:00:00",
                "end": "2026-11-10T10:00:00",
                "user": "tester",
            },
        )
        assert res.status_code == 422


def test_single_booking_end_before_or_equal_to_start_rejected(booking_client):
    """verifies that start == end (0 duration) or end < start is rejected with 422"""
    client, _ = booking_client
    res_equal = client.post(
        "/api/v1/bookings",
        json={
            "room_id": 3,
            "start": "2026-11-10T09:00:00",
            "end": "2026-11-10T09:00:00",
            "user": "tester",
        },
    )
    assert res_equal.status_code == 422
    assert (
        "end datetime must be strictly after start datetime"
        in res_equal.json()["detail"]
    )

    res_inverted = client.post(
        "/api/v1/bookings",
        json={
            "room_id": 3,
            "start": "2026-11-10T10:00:00",
            "end": "2026-11-10T09:00:00",
            "user": "tester",
        },
    )
    assert res_inverted.status_code == 422
    assert (
        "end datetime must be strictly after start datetime"
        in res_inverted.json()["detail"]
    )


def test_single_booking_offset_timezone_rejected(booking_client):
    """verifies that iso timestamps containing utc offsets or 'z' are rejected with 422"""
    client, _ = booking_client
    for offset_ts in [
        "2026-11-10T09:00:00Z",
        "2026-11-10T09:00:00+01:00",
        "2026-11-10T09:00:00-07:00",
    ]:
        res = client.post(
            "/api/v1/bookings",
            json={
                "room_id": 3,
                "start": offset_ts,
                "end": "2026-11-10T10:00:00",
                "user": "tester",
            },
        )
        assert res.status_code == 422


def test_different_rooms_simultaneous_booking_succeeds(booking_client):
    """verifies that different rooms can be booked for the exact same time without conflict"""
    client, _ = booking_client
    res_room3 = client.post(
        "/api/v1/bookings",
        json={
            "room_id": 3,
            "start": "2026-11-10T10:00:00",
            "end": "2026-11-10T11:00:00",
            "user": "alice",
        },
    )
    assert res_room3.status_code == 201

    res_room4 = client.post(
        "/api/v1/bookings",
        json={
            "room_id": 4,
            "start": "2026-11-10T10:00:00",
            "end": "2026-11-10T11:00:00",
            "user": "bob",
        },
    )
    assert res_room4.status_code == 201


def test_single_booking_comprehensive_conflict_intervals(booking_client):
    """exhaustively tests half-open interval conflict boundaries against [10:00, 11:00)"""
    client, _ = booking_client
    base = client.post(
        "/api/v1/bookings",
        json={
            "room_id": 3,
            "start": "2026-11-10T10:00:00",
            "end": "2026-11-10T11:00:00",
            "user": "base-booking",
        },
    )
    assert base.status_code == 201

    conflict_scenarios = [
        ("2026-11-10T09:30:00", "2026-11-10T10:30:00"),  # starts before, ends inside
        ("2026-11-10T10:30:00", "2026-11-10T11:30:00"),  # starts inside, ends after
        ("2026-11-10T10:15:00", "2026-11-10T10:45:00"),  # internal sub-interval
        ("2026-11-10T09:30:00", "2026-11-10T11:30:00"),  # completely enclosing
        ("2026-11-10T10:00:00", "2026-11-10T11:00:00"),  # exact duplicate
    ]
    for start_t, end_t in conflict_scenarios:
        res = client.post(
            "/api/v1/bookings",
            json={
                "room_id": 3,
                "start": start_t,
                "end": end_t,
                "user": "conflict-attempter",
            },
        )
        assert res.status_code == 409
        assert "Conflict detected" in res.json()["detail"]


def test_recurring_booking_exceeds_52_weeks_limit_rejected(booking_client):
    """verifies that repeat_until exceeding 52 weeks is rejected with 422"""
    client, _ = booking_client
    res = client.post(
        "/api/v1/bookings/recurring",
        json={
            "room_id": 3,
            "start": "2026-11-04T10:00:00",
            "end": "2026-11-04T11:00:00",
            "user": "ultra-long",
            "repeat_until": "2027-11-20",  # > 366 days
        },
    )
    assert res.status_code == 422
    assert "exceeds 52 weeks maximum allowed limit" in res.json()["detail"]


def test_recurring_booking_single_instance_succeeds(booking_client):
    """verifies that a 1-instance recurring series (repeat_until == end.date()) succeeds with 201"""
    client, _ = booking_client
    res = client.post(
        "/api/v1/bookings/recurring",
        json={
            "room_id": 3,
            "start": "2026-11-10T14:00:00",
            "end": "2026-11-10T15:00:00",
            "user": "single-instance-series",
            "repeat_until": "2026-11-10",
        },
    )
    assert res.status_code == 201
    data = res.json()
    assert data["total_requested"] == 1
    assert data["created_count"] == 1
    assert data["skipped_count"] == 0
    assert len(data["created"]) == 1


def test_recurring_booking_single_instance_conflict_rolls_back(booking_client):
    """verifies that a 1-instance recurring series with a conflict rolls back (0% success < 50%)"""
    client, _ = booking_client
    client.post(
        "/api/v1/bookings",
        json={
            "room_id": 3,
            "start": "2026-11-10T14:00:00",
            "end": "2026-11-10T15:00:00",
            "user": "existing",
        },
    )

    res = client.post(
        "/api/v1/bookings/recurring",
        json={
            "room_id": 3,
            "start": "2026-11-10T14:00:00",
            "end": "2026-11-10T15:00:00",
            "user": "single-conflict",
            "repeat_until": "2026-11-10",
        },
    )
    assert res.status_code == 409
    assert "conflicts exceed threshold" in res.json()["detail"]


def test_recurring_booking_3_instances_1_conflict_succeeds(booking_client):
    """verifies that a 3-instance series with 1 conflict (67% success >= 50%) succeeds with 1 skipped"""
    client, _ = booking_client
    client.post(
        "/api/v1/bookings",
        json={
            "room_id": 4,
            "start": "2026-11-11T10:00:00",
            "end": "2026-11-11T11:00:00",
            "user": "blocker-week2",
        },
    )

    res = client.post(
        "/api/v1/bookings/recurring",
        json={
            "room_id": 4,
            "start": "2026-11-04T10:00:00",
            "end": "2026-11-04T11:00:00",
            "user": "three-weeks-booker",
            "repeat_until": "2026-11-18",
        },
    )
    assert res.status_code == 201
    data = res.json()
    assert data["total_requested"] == 3
    assert data["created_count"] == 2
    assert data["skipped_count"] == 1


def test_recurring_booking_3_instances_2_conflicts_rolls_back(booking_client):
    """verifies that a 3-instance series with 2 conflicts (33% success < 50%) triggers atomic rollback with 409"""
    client, _ = booking_client
    client.post(
        "/api/v1/bookings",
        json={
            "room_id": 4,
            "start": "2026-11-04T10:00:00",
            "end": "2026-11-04T11:00:00",
            "user": "blocker-week1",
        },
    )
    client.post(
        "/api/v1/bookings",
        json={
            "room_id": 4,
            "start": "2026-11-11T10:00:00",
            "end": "2026-11-11T11:00:00",
            "user": "blocker-week2",
        },
    )

    res = client.post(
        "/api/v1/bookings/recurring",
        json={
            "room_id": 4,
            "start": "2026-11-04T10:00:00",
            "end": "2026-11-04T11:00:00",
            "user": "three-weeks-fail",
            "repeat_until": "2026-11-18",
        },
    )
    assert res.status_code == 409
    assert "conflicts exceed threshold" in res.json()["detail"]


def test_recurring_booking_dst_winter_transition_preserves_wall_clock(booking_client):
    """verifies recurring booking across denver dst transition (2026-11-01) retains local wall time 09:00:00 (om-2)"""
    client, _ = booking_client
    res = client.post(
        "/api/v1/bookings/recurring",
        json={
            "room_id": 4,
            "start": "2026-10-21T09:00:00",
            "end": "2026-10-21T10:00:00",
            "user": "denver-team",
            "repeat_until": "2026-11-18",
        },
    )
    assert res.status_code == 201
    data = res.json()
    assert data["total_requested"] == 5
    assert data["created_count"] == 5
    for instance in data["created"]:
        assert instance["start"].endswith("T09:00:00")
        assert instance["end"].endswith("T10:00:00")
