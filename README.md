# RoomLoop — Meeting Room Booking Core Service

A production-grade meeting room booking core service written in Python 3.12, FastAPI, and SQLAlchemy 2.0+, built according to strict Clean Architecture principles.

Designed specifically to eliminate concurrency double-bookings, multi-office daylight saving time (DST) shifts between Berlin and Denver, and orphaned recurring series.

---

## Key Highlights

- **Clean Class-Based Architecture**: Separation of concerns across Domain Contracts (Pydantic v2 DTOs), ORM Models (SQLAlchemy 2.0 mapped columns), Persistence Repositories, Domain Business Services, HTTP Controllers, and FastApi Routers.
- **Strict Concurrency Guarantees**: SQLite Write-Ahead Logging (`PRAGMA journal_mode=WAL`) coupled with eager `BEGIN IMMEDIATE` transaction write locks that eliminate race conditions and serialize conflict checks without double bookings.
- **Multi-Office Wall-Clock Stability**: Room-local naive ISO timestamp storage (`YYYY-MM-DDTHH:MM:SS`) preserving meeting wall-clock times (e.g. `09:00:00`) across DST transitions in both `Europe/Berlin` and `America/Denver` without UTC offset drift.
- **Conflict Policy (R1/R2 Reconciliation)**: Upfront recurrence expansion governed by the **50% + Max 2 Conflict Policy**—at most 2 conflicting instances are skipped per series provided at least 50% and at least 1 booking succeeds; otherwise an atomic all-or-nothing rollback occurs.
- **Series Cancellation & Historical Preservation (OM-1)**: `DELETE /series/{id}` soft-deletes future occurrences based on room-local current time while leaving past and in-progress meetings intact for audit reporting. Frees room slots immediately.
- **Dual-Layer Logging**: Real-time structured application logs alongside an immutable SQLite `audit_logs` table tracking every booking creation, skip, rollback, and cancellation.

---

## System Architecture

```text
src/roomloop/
├── api/
│   └── v1/
│       └── router.py                 # Top-level API v1 router mounting feature modules
├── config/
│   ├── env.py                        # Strict Pydantic environment configuration (Zod pattern)
│   ├── database.py                   # Engine lifecycle, SQLite WAL pragma, BEGIN IMMEDIATE hook
│   └── fastapi.py                    # FastApi application factory and middleware configuration
├── modules/
│   ├── audit/                        # Audit domain module
│   │   ├── model.py                  # AuditLogModel SQLAlchemy entity
│   │   ├── repository.py             # AuditLogRepository persistence operations
│   │   └── service.py                # AuditService query access
│   ├── bookings/                     # Booking domain module
│   │   ├── contract.py               # Pydantic request & response DTOs (extra='forbid')
│   │   ├── controller.py             # HTTP endpoint request/response coordinator
│   │   ├── model.py                  # SeriesModel & BookingModel SQLAlchemy entities
│   │   ├── repository.py             # Conflict detection, creation, and soft-deletion queries
│   │   ├── routes.py                 # FastApi route bindings (/bookings, /series)
│   │   └── service.py                # Business logic: DST validation, 50% rule, atomic transactions
│   └── rooms/                        # Rooms domain module
│       ├── contract.py               # RoomResponse DTO strictly enforcing Contract C2
│       ├── controller.py             # RoomController
│       ├── model.py                  # RoomModel persistent entity
│       ├── repository.py             # RoomRepository with session-reuse support
│       ├── routes.py                 # FastApi route bindings (/rooms)
│       └── service.py                # RoomService
├── seeding/
│   ├── __main__.py                   # Standalone seed CLI runner
│   └── seeder.py                     # Idempotent seeder for prototype rooms (3, 4, 9, 17)
├── shared/
│   ├── middlewares/
│   │   └── request_logger.py         # HTTP latency and request logging middleware
│   ├── models/
│   │   └── base.py                   # DeclarativeBase for SQLAlchemy ORM
│   ├── services/
│   │   └── logger.py                 # Structured application stream logger
│   └── utils/
│       └── time.py                   # Strict ISO parsing, DST gap/fold checks, weekly recurrence
└── server.py                         # Application Composition Root and Uvicorn runner
```

---

## Quickstart

### Prerequisites

- **Python 3.12+**
- **uv** (ultra-fast Python package and project manager)

```bash
# install uv if not already present
curl -LsSf https://astral.sh/uv/install.sh | sh
```

### 1. Installation

Clone the repository and sync dependencies:

```bash
git clone <repository_url>
cd AuricAiRoomLoopTask
uv sync
```

### 2. Seed Database

Initialize the database schema and populate the prototype rooms (`[3, 4, 9, 17]`):

```bash
make seed
```

_(Alternatively: `uv run python -m roomloop.seeding`)_

### 3. Run the Development Server

Start the REST API service on `http://localhost:8000`:

```bash
make dev
```

_(Alternatively: `uv run python -m roomloop.server` or `uv run python main.py`)_

Interactive OpenAPI Swagger documentation is available at:
**[http://localhost:8000/docs](http://localhost:8000/docs)**

---

## Make Commands Reference

| Command             | Action                                                                     |
| ------------------- | -------------------------------------------------------------------------- |
| `make dev`          | Start development server on `localhost:8000`                               |
| `make start`        | Start production server                                                    |
| `make seed`         | Idempotently seed prototype rooms into SQLite                              |
| `make test`         | Run complete pytest test suite                                             |
| `make test-v`       | Run pytest suite with verbose output                                       |
| `make lint`         | Run Ruff linter checks across `src/` and `tests/`                          |
| `make format`       | Auto-format codebase using Ruff                                            |
| `make format-check` | Check code formatting compliance                                           |
| `make verify`       | Run full quality gate: linter, format-check, and 55 unit/integration tests |
| `make clean`        | Clean build artifacts, pycache, and temporary test databases               |

---

## REST API Specification

### 1. List Rooms (`GET /rooms` or `GET /api/v1/rooms`)

Complies strictly with Contract C2 returning only `id`, `name`, and `capacity`.

```bash
curl -X GET http://localhost:8000/rooms
```

**Response (`200 OK`)**:

```json
[
  { "id": 3, "name": "Neukölln", "capacity": 8 },
  { "id": 4, "name": "Kreuzberg", "capacity": 12 },
  { "id": 9, "name": "LoDo", "capacity": 6 },
  { "id": 17, "name": "RiNo", "capacity": 16 }
]
```

---

### 2. Create Single Booking (`POST /bookings`)

Creates a single booking instance. Validates room existence, DST gap validity, and zero half-open interval conflicts.

```bash
curl -X POST http://localhost:8000/bookings \
  -H "Content-Type: application/json" \
  -d '{
    "room_id": 3,
    "start": "2026-11-10T09:00:00",
    "end": "2026-11-10T10:00:00",
    "user": "alice"
  }'
```

**Response (`201 Created`)**:

```json
{
  "id": 1,
  "room_id": 3,
  "series_id": null,
  "user": "alice",
  "start": "2026-11-10T09:00:00",
  "end": "2026-11-10T10:00:00",
  "status": "active",
  "created_at_utc": "2026-10-21T15:40:00.123456+00:00"
}
```

---

### 3. Create Recurring Booking (`POST /bookings/recurring`)

Generates weekly occurrences upfront until `repeat_until`. Applies the **50% + Max 2 Conflict Rule**.

```bash
curl -X POST http://localhost:8000/bookings/recurring \
  -H "Content-Type: application/json" \
  -d '{
    "room_id": 4,
    "start": "2026-11-04T14:00:00",
    "end": "2026-11-04T15:00:00",
    "user": "engineering-team",
    "repeat_until": "2026-11-25"
  }'
```

**Response (`201 Created`)**:

```json
{
  "series_id": 1,
  "total_requested": 4,
  "created_count": 4,
  "skipped_count": 0,
  "created": [
    {
      "id": 2,
      "room_id": 4,
      "series_id": 1,
      "user": "engineering-team",
      "start": "2026-11-04T14:00:00",
      "end": "2026-11-04T15:00:00",
      "status": "active",
      "created_at_utc": "..."
    }
  ],
  "skipped": []
}
```

---

### 4. Cancel Single Booking (`DELETE /bookings/{id}`)

Soft-deletes an individual booking and frees the slot immediately for new bookings.

```bash
curl -X DELETE http://localhost:8000/bookings/1
```

**Response (`200 OK`)**:

```json
{
  "id": 1,
  "status": "cancelled",
  "cancelled_at_utc": "2026-10-21T15:45:00.000000+00:00"
}
```

---

### 5. Cancel Recurring Series (`DELETE /series/{series_id}` or `DELETE /bookings/series/{series_id}`)

Resolves Office Manager complaint OM-1. Cancels all future instances of an abandoned series based on current time in the room's timezone, preserving past and in-progress meetings for reporting.

```bash
curl -X DELETE http://localhost:8000/series/1
```

**Response (`200 OK`)**:

```json
{
  "series_id": 1,
  "cancelled_count": 4,
  "kept_count": 0,
  "cancelled_at_utc": "2026-10-21T15:50:00.000000+00:00"
}
```

---

### 6. Health Check (`GET /health`)

```bash
curl -X GET http://localhost:8000/health
```

**Response (`200 OK`)**:

```json
{
  "status": "ok",
  "environment": "development",
  "database": "connected"
}
```

---

## Concurrency & Data Integrity

In SQLite, transactions default to `DEFERRED`, meaning write locks are delayed until a mutation query executes. If two concurrent requests check for overlapping meetings simultaneously, both could find zero conflicts and insert overlapping rows.

RoomLoop eliminates this race condition via two database lifecycle event hooks in `DatabaseConnection`:

1. `PRAGMA journal_mode = WAL`: Enables Write-Ahead Logging for high-throughput concurrent readers.
2. `BEGIN IMMEDIATE` Hook: Eagerly acquires an exclusive write lock at transaction start, serializing concurrent booking attempts before overlap checks take place.

Verified with 8 concurrent worker threads in `tests/test_concurrency.py`: exactly 1 request succeeds (201 Created) and 7 are rejected (409 Conflict), guaranteeing zero double-bookings.

---

## Test Suite & Verification

The test suite covers **55 automated tests** across 11 test modules:

```bash
$ make verify
uv run ruff check src tests
All checks passed!
uv run ruff format --check src tests
48 files already formatted
uv run pytest
============================== 55 passed in 1.65s ==============================
```

### Risk Scenarios Tested

- **Denver DST Transition**: Recurring bookings retain `09:00:00` wall-clock time across the 2026-11-01 Denver DST boundary (`test_denver_dst_transition_preserves_wall_clock_time`).
- **Berlin DST Transition**: Recurring bookings retain `09:00:00` wall-clock time across the 2026-10-25 Berlin DST boundary (`test_berlin_dst_transition_preserves_wall_clock_time`).
- **Spring-Forward DST Gaps**: Rejects non-existent local wall times (e.g. Berlin 02:30 on 2027-03-28) with 422 (`test_single_booking_dst_gap_rejected`).
- **R1/R2 Conflict Threshold**: Verifies 4-week series with 2 conflicts succeeds with 2 skipped (50% rule), while 2-week series with 2 conflicts (0% success) or 10-week series with 3 conflicts ($>2$) triggers atomic rollback (`tests/test_bookings.py`).
- **Series Cancellation & Historical Preservation**: Verifies future series instances are cancelled, past instances are kept intact, and cancelled slots are immediately bookable again (`tests/test_cancellation.py`).
- **Contract C2 Integrity**: Verifies `GET /rooms` returns exact JSON keys `{id, name, capacity}` for prototype IDs `3, 4, 9, 17` (`tests/test_rooms.py`).
- **Refutation of Sequential Room IDs**: Non-existent rooms `1` and `2` return 404; code does not assume `1..N` (`test_r5_sequential_assumption_refuted`).
- **High Concurrency Serialization**: 8 simultaneous worker threads attempting to book the exact same slot result in exactly 1 success and 7 rejections without database corruption (`tests/test_concurrency.py`).
- **Audit Trail Immutability**: All creation, skip, rollback, and cancellation events are verified in the `audit_logs` table (`tests/test_audit.py`).
