"""
Payload bank generator for RoomLoop k6 load testing suite.

Generates 5,000 realistic HTTP request templates across all API capabilities:
- Reads: Facilities dashboard (GET /rooms, Contract C2), GET /api/v1/rooms, GET /health
- Valid single & recurring reservations with 4-year random timestamp ranges
- Bad room IDs (404 Not Found)
- Validation errors: Inverted time intervals, DST gap hours, malformed ISO strings (422)
- Extra forbidden fields (Pydantic extra="forbid" -> 422)
- Single deletion & series deletion (200, 204, 400, 404)
- Dynamic placeholder tokens (##...) resolved at runtime by k6
"""

from __future__ import annotations

import json
import random
from pathlib import Path

SEED_PROTOTYPE_ROOM_IDS = [3, 4, 9, 17]
INVALID_ROOM_IDS = [999, 1001, 4040, 777, 1, 2, 5, 8]
SAMPLE_USERS = [
    "alex",
    "sam",
    "jordan",
    "taylor",
    "morgan",
    "casey",
    "charlie",
    "pat",
    "elena",
    "marcus",
    "priya",
    "david",
    "sophia",
    "liam",
]


def generate_payload_bank(count: int = 5000) -> list[dict[str, object]]:
    """generates count structured request templates with metadata and dynamic placeholders"""
    items: list[dict[str, object]] = []

    # Distribution weights (total 100 percent):
    # - 50 percent reads (dashboard C2, rooms, health)
    # - 25 percent single bookings (valid + 404s + 422s)
    # - 15 percent recurring series (valid + 404s + 422s)
    # - 7 percent deletions (series and single)
    # - 3 percent edge cases and unknown routes

    read_count = int(count * 0.50)  # 2500
    single_count = int(count * 0.25)  # 1250
    recurring_count = int(count * 0.15)  # 750
    delete_count = int(count * 0.07)  # 350
    edge_count = count - (
        read_count + single_count + recurring_count + delete_count
    )  # 150

    item_id = 1

    # 1. READ REQUESTS (2500)
    for _ in range(read_count):
        sub_type = random.choices(
            ["c2_rooms", "v1_rooms", "health"], weights=[40, 20, 40]
        )[0]
        if sub_type == "c2_rooms":
            items.append(
                {
                    "id": item_id,
                    "name": "read_c2_facilities_dashboard",
                    "method": "GET",
                    "path": "/rooms",
                    "headers": {"X-Request-ID": "##request_id"},
                    "body": None,
                    "expected_statuses": [200],
                }
            )
        elif sub_type == "v1_rooms":
            items.append(
                {
                    "id": item_id,
                    "name": "read_v1_rooms_inventory",
                    "method": "GET",
                    "path": "/api/v1/rooms",
                    "headers": {"X-Request-ID": "##request_id"},
                    "body": None,
                    "expected_statuses": [200],
                }
            )
        else:
            items.append(
                {
                    "id": item_id,
                    "name": "read_health_probe",
                    "method": "GET",
                    "path": "/health",
                    "headers": {"X-Request-ID": "##request_id"},
                    "body": None,
                    "expected_statuses": [200],
                }
            )
        item_id += 1

    # 2. SINGLE BOOKING REQUESTS (1250)
    for _ in range(single_count):
        sub_type = random.choices(
            [
                "valid_booking",
                "nonexistent_room",
                "inverted_interval",
                "dst_gap_time",
                "extra_forbidden_field",
                "malformed_timestamp",
            ],
            weights=[80, 8, 4, 3, 3, 2],
        )[0]

        if sub_type == "valid_booking":
            items.append(
                {
                    "id": item_id,
                    "name": "single_booking_valid",
                    "method": "POST",
                    "path": "/api/v1/bookings",
                    "headers": {
                        "Content-Type": "application/json",
                        "X-Request-ID": "##request_id",
                    },
                    "body": {
                        "room_id": "##valid_room_id",
                        "start": "##random_timestamp_start_4yr",
                        "end": "##random_timestamp_end_4yr",
                        "user": "##random_user",
                    },
                    "expected_statuses": [201, 409],
                }
            )
        elif sub_type == "nonexistent_room":
            items.append(
                {
                    "id": item_id,
                    "name": "single_booking_nonexistent_room",
                    "method": "POST",
                    "path": "/api/v1/bookings",
                    "headers": {
                        "Content-Type": "application/json",
                        "X-Request-ID": "##request_id",
                    },
                    "body": {
                        "room_id": "##invalid_room_id",
                        "start": "##random_timestamp_start_4yr",
                        "end": "##random_timestamp_end_4yr",
                        "user": "##random_user",
                    },
                    "expected_statuses": [404],
                }
            )
        elif sub_type == "inverted_interval":
            items.append(
                {
                    "id": item_id,
                    "name": "single_booking_inverted_interval",
                    "method": "POST",
                    "path": "/api/v1/bookings",
                    "headers": {
                        "Content-Type": "application/json",
                        "X-Request-ID": "##request_id",
                    },
                    "body": {
                        "room_id": "##valid_room_id",
                        "start": "##inverted_start",
                        "end": "##inverted_end",
                        "user": "##random_user",
                    },
                    "expected_statuses": [422],
                }
            )
        elif sub_type == "dst_gap_time":
            items.append(
                {
                    "id": item_id,
                    "name": "single_booking_spring_forward_gap",
                    "method": "POST",
                    "path": "/api/v1/bookings",
                    "headers": {
                        "Content-Type": "application/json",
                        "X-Request-ID": "##request_id",
                    },
                    "body": {
                        "room_id": 3,  # Neukölln (Europe/Berlin)
                        "start": "##spring_forward_gap_time",
                        "end": "##spring_forward_gap_end",
                        "user": "##random_user",
                    },
                    "expected_statuses": [422],
                }
            )
        elif sub_type == "extra_forbidden_field":
            items.append(
                {
                    "id": item_id,
                    "name": "single_booking_extra_field_forbidden",
                    "method": "POST",
                    "path": "/api/v1/bookings",
                    "headers": {
                        "Content-Type": "application/json",
                        "X-Request-ID": "##request_id",
                    },
                    "body": {
                        "room_id": "##valid_room_id",
                        "start": "##random_timestamp_start_4yr",
                        "end": "##random_timestamp_end_4yr",
                        "user": "##random_user",
                        "unauthorized_field": "##extra_field_value",
                    },
                    "expected_statuses": [422],
                }
            )
        else:  # malformed_timestamp
            items.append(
                {
                    "id": item_id,
                    "name": "single_booking_malformed_timestamp",
                    "method": "POST",
                    "path": "/api/v1/bookings",
                    "headers": {
                        "Content-Type": "application/json",
                        "X-Request-ID": "##request_id",
                    },
                    "body": {
                        "room_id": "##valid_room_id",
                        "start": "##malformed_timestamp",
                        "end": "##random_timestamp_end_4yr",
                        "user": "##random_user",
                    },
                    "expected_statuses": [422],
                }
            )
        item_id += 1

    # 3. RECURRING SERIES REQUESTS (750)
    for _ in range(recurring_count):
        sub_type = random.choices(
            [
                "valid_recurring",
                "nonexistent_room",
                "repeat_before_end",
                "excessive_horizon",
                "extra_forbidden_field",
            ],
            weights=[80, 8, 4, 4, 4],
        )[0]

        if sub_type == "valid_recurring":
            items.append(
                {
                    "id": item_id,
                    "name": "recurring_booking_valid",
                    "method": "POST",
                    "path": "/api/v1/bookings/recurring",
                    "headers": {
                        "Content-Type": "application/json",
                        "X-Request-ID": "##request_id",
                    },
                    "body": {
                        "room_id": "##valid_room_id",
                        "start": "##random_timestamp_start_4yr",
                        "end": "##random_timestamp_end_4yr",
                        "repeat_until": "##random_repeat_until_4yr",
                        "user": "##random_user",
                    },
                    "expected_statuses": [201, 409],
                }
            )
        elif sub_type == "nonexistent_room":
            items.append(
                {
                    "id": item_id,
                    "name": "recurring_booking_nonexistent_room",
                    "method": "POST",
                    "path": "/api/v1/bookings/recurring",
                    "headers": {
                        "Content-Type": "application/json",
                        "X-Request-ID": "##request_id",
                    },
                    "body": {
                        "room_id": "##invalid_room_id",
                        "start": "##random_timestamp_start_4yr",
                        "end": "##random_timestamp_end_4yr",
                        "repeat_until": "##random_repeat_until_4yr",
                        "user": "##random_user",
                    },
                    "expected_statuses": [404],
                }
            )
        elif sub_type == "repeat_before_end":
            items.append(
                {
                    "id": item_id,
                    "name": "recurring_booking_repeat_before_end",
                    "method": "POST",
                    "path": "/api/v1/bookings/recurring",
                    "headers": {
                        "Content-Type": "application/json",
                        "X-Request-ID": "##request_id",
                    },
                    "body": {
                        "room_id": "##valid_room_id",
                        "start": "##random_timestamp_start_4yr",
                        "end": "##random_timestamp_end_4yr",
                        "repeat_until": "##repeat_before_end",
                        "user": "##random_user",
                    },
                    "expected_statuses": [422],
                }
            )
        elif sub_type == "excessive_horizon":
            items.append(
                {
                    "id": item_id,
                    "name": "recurring_booking_excessive_horizon",
                    "method": "POST",
                    "path": "/api/v1/bookings/recurring",
                    "headers": {
                        "Content-Type": "application/json",
                        "X-Request-ID": "##request_id",
                    },
                    "body": {
                        "room_id": "##valid_room_id",
                        "start": "##random_timestamp_start_4yr",
                        "end": "##random_timestamp_end_4yr",
                        "repeat_until": "##excessive_repeat_horizon",
                        "user": "##random_user",
                    },
                    "expected_statuses": [422],
                }
            )
        else:
            items.append(
                {
                    "id": item_id,
                    "name": "recurring_booking_extra_field_forbidden",
                    "method": "POST",
                    "path": "/api/v1/bookings/recurring",
                    "headers": {
                        "Content-Type": "application/json",
                        "X-Request-ID": "##request_id",
                    },
                    "body": {
                        "room_id": "##valid_room_id",
                        "start": "##random_timestamp_start_4yr",
                        "end": "##random_timestamp_end_4yr",
                        "repeat_until": "##random_repeat_until_4yr",
                        "user": "##random_user",
                        "forbidden_recurrence_rule": "RRULE:FREQ=DAILY",
                    },
                    "expected_statuses": [422],
                }
            )
        item_id += 1

    # 4. DELETION REQUESTS (350)
    for _ in range(delete_count):
        sub_type = random.choices(["delete_series", "delete_single"], weights=[60, 40])[
            0
        ]
        if sub_type == "delete_series":
            items.append(
                {
                    "id": item_id,
                    "name": "delete_series_by_id",
                    "method": "DELETE",
                    "path": "/api/v1/bookings/series/##random_series_id",
                    "headers": {"X-Request-ID": "##request_id"},
                    "body": None,
                    "expected_statuses": [200, 404],
                }
            )
        else:
            items.append(
                {
                    "id": item_id,
                    "name": "delete_single_booking_by_id",
                    "method": "DELETE",
                    "path": "/api/v1/bookings/##random_booking_id",
                    "headers": {"X-Request-ID": "##request_id"},
                    "body": None,
                    "expected_statuses": [200, 400, 404],
                }
            )
        item_id += 1

    # 5. EDGE CASES & 404 PROBES (150)
    for _ in range(edge_count):
        route_suffix = random.choice(
            [
                "unknown_path",
                "v1/non_existent_resource",
                "prototype_legacy_test",
                "internal/debug",
            ]
        )
        items.append(
            {
                "id": item_id,
                "name": "probe_unknown_route",
                "method": "GET",
                "path": f"/api/{route_suffix}",
                "headers": {"X-Request-ID": "##request_id"},
                "body": None,
                "expected_statuses": [404],
            }
        )
        item_id += 1

    return items


def main() -> None:
    output_dir = Path(__file__).parent
    output_file = output_dir / "payloads.json"
    print("Generating 5,000 diverse payload templates for k6 load testing...")
    payloads = generate_payload_bank(5000)
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(payloads, f, indent=2)
    print(f"Successfully generated {len(payloads)} request templates at: {output_file}")


if __name__ == "__main__":
    main()
