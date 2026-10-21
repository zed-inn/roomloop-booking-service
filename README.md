# RoomLoop — Meeting Room Booking Core Service

RoomLoop is a meeting room booking core service built with **Python 3.12**, **FastAPI**, and **SQLAlchemy 2.0+**.

The service was redesigned and rebuilt from scratch to replace an earlier prototype that suffered from three major issues:

1. **Concurrency Race Conditions**: Concurrent requests could book the same room at the same time, leading to double bookings.
2. **Multi-Office Timezone Drift**: Denver meetings drifted by one hour every winter because UTC conversions failed to account for regional daylight saving time (DST) shifts between Berlin and Denver.
3. **Orphaned Recurring Bookings**: Teams dissolved, leaving recurring bookings occupying rooms indefinitely with no easy way to cancel future slots while keeping past records for reporting.

---

## Quickstart

### Prerequisites

- **Python 3.12+**
- **uv** (fast Python package and project manager)

```bash
# install uv if not already installed
curl -LsSf https://astral.sh/uv/install.sh | sh
```

### 1. Installation

Clone the repository and install dependencies:

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

> [!IMPORTANT]
> Always run `make seed` before starting the server. Seeding is decoupled from the server startup sequence so that deployments never inadvertently mutate existing data.

### 3. Start the Server

Run the development server on `http://localhost:8000`:

```bash
make dev
```

Interactive OpenAPI documentation is available at: **[http://localhost:8000/docs](http://localhost:8000/docs)**

---

## Project Architecture

The codebase follows a modular Clean Architecture where business rules, database queries, and HTTP concerns are strictly separated:

```text
src/roomloop/
├── api/
│   └── v1/
│       └── router.py                 # API v1 top-level router mounting all domain modules
├── config/
│   ├── env.py                        # Environment variable validation with strict types
│   ├── database.py                   # Engine configuration, SQLite WAL mode, BEGIN IMMEDIATE lock
│   └── fastapi.py                    # FastAPI application factory and middleware registration
├── modules/
│   ├── audit/                        # Audit domain: logs all booking creations, skips, cancellations
│   │   ├── model.py                  # AuditLogModel entity
│   │   ├── repository.py             # Append-only audit persistence
│   │   └── service.py                # Audit querying service
│   ├── bookings/                     # Booking domain: single & recurring reservations
│   │   ├── contract.py               # Pydantic request & response DTOs (extra="forbid")
│   │   ├── controller.py             # HTTP request dispatchers
│   │   ├── model.py                  # SeriesModel & BookingModel ORM entities
│   │   ├── repository.py             # Half-open interval conflict detection and queries
│   │   ├── routes.py                 # FastApi route bindings (/api/v1/bookings)
│   │   └── service.py                # Business logic: DST validation, 50% rule, atomic transactions
│   └── rooms/                        # Rooms domain: facilities inventory
│       ├── contract.py               # RoomResponse DTO strictly adhering to Contract C2
│       ├── controller.py             # RoomController
│       ├── model.py                  # RoomModel ORM entity
│       ├── repository.py             # Room lookup with active session reuse
│       ├── routes.py                 # FastApi route bindings (/rooms, /api/v1/rooms)
│       └── service.py                # Room querying service
├── seeding/
│   ├── __main__.py                   # Standalone seed CLI runner
│   └── seeder.py                     # Idempotent room seeder
├── shared/
│   ├── middlewares/
│   │   └── request_logger.py         # Request latency and HTTP traffic logger
│   ├── models/
│   │   ├── base.py                   # SQLAlchemy DeclarativeBase
│   │   └── registry.py               # Dynamic model registry loading schemas into Base metadata
│   ├── services/
│   │   └── logger.py                 # Structured application stream logger
│   └── utils/
│       └── time.py                   # Strict ISO parsing, DST gap/fold checks, weekly recurrence
└── server.py                         # Application Composition Root and Uvicorn server runner
```

---

## Core Engineering Solutions

### 1. Zero Double-Bookings under Concurrency (`BEGIN IMMEDIATE` + WAL)

In SQLite, transactions run in `DEFERRED` mode by default, meaning write locks are only acquired when a `INSERT` or `UPDATE` is issued. If two users check for available slots at the exact same moment, both read queries see the slot as free before either writes, resulting in double bookings.

**How we solved it**:

1. Enabled Write-Ahead Logging (`PRAGMA journal_mode=WAL`), allowing simultaneous readers without blocking writers.
2. Hooked a `BEGIN IMMEDIATE` listener into SQLAlchemy's engine that immediately acquires an exclusive write lock at the start of any booking transaction.

This serializes conflicting requests before overlap checks execute. Tested with 8 concurrent worker threads: exactly 1 booking succeeds and 7 fail with `409 Conflict`, with zero double bookings.

### 2. Multi-Office Wall-Clock Time Stability (Solving Denver's Winter Drift)

The company has offices in Berlin (`Europe/Berlin`) and Denver (`America/Denver`). Converting meeting times to UTC and adding 7 days in seconds causes local meeting times to drift by an hour when regional DST transition dates do not align.

**How we solved it**:

1. Stored all timestamps as naive local ISO strings (`YYYY-MM-DDTHH:MM:SS`) in the room's timezone, satisfying Contract C1 for the nightly reporting script.
2. Handled weekly recurrence by adding 7 calendar days directly to the local wall-clock time (`current_start + timedelta(days=7)`), ensuring a 09:00 meeting stays at 09:00 local time year-round.
3. Verified local times against `zoneinfo.ZoneInfo` to reject non-existent spring-forward transition times (e.g., 02:30 during Berlin spring-forward) with `422 Unprocessable Entity`.

### 3. Recurring Booking Conflict Policy ("50% + Max 2 Conflict" Rule)

The brief presented an apparent contradiction: Rule R1 requires recurring bookings to be all-or-nothing, while Rule R2 allows skipping up to 2 conflicting instances.

**How we reconciled them**:
A series is accepted if and only if:

- Conflicts $\le 2$ (Rule R2).
- At least 50% of requested bookings succeed.
- At least 1 booking is created.

If more than 2 instances conflict or the success rate drops below 50%, an atomic rollback occurs returning `409 Conflict` (Rule R1).

### 4. Series Cancellation & Historical Preservation (Solving OM-1)

When an abandoned recurring series is cancelled via `DELETE /api/v1/bookings/series/{id}`:

- The system checks the current time in the room's timezone.
- Meetings already concluded or underway remain `status="active"` for historical reporting (Contract C1).
- All future meetings are soft-deleted (`status="cancelled"`), immediately freeing those slots for new bookings.

Individual occurrences of a recurring series cannot be cancelled via `DELETE /api/v1/bookings/{id}` (`400 Bad Request`); cancelling a series must cancel all future occurrences to preserve series integrity.

### 5. Non-Blocking Asynchronous Queue Logging & Environment Isolation

- **Non-blocking logging**: Real-time logging utilizes Python's standard `QueueHandler` and `QueueListener` on a dedicated background thread. Requests push log records instantaneously into an in-memory queue, ensuring stdout terminal I/O latency never blocks async HTTP request loops.
- **Strict environment isolation**: `make start` runs with `ENVIRONMENT=production`, `make dev` runs with `ENVIRONMENT=development`, and test runs (`make test`, `make test-v`, `make verify`) strictly enforce `ENVIRONMENT=test`.

---

## REST API Reference

### 1. List Rooms (`GET /rooms` or `GET /api/v1/rooms`)

Complies strictly with Contract C2, returning only `id`, `name`, and `capacity` so external dashboards never break.

```bash
curl -X GET http://localhost:8000/rooms
```

**Response (`200 OK`)**:

```json
[
  { "id": 3, "name": "Neukölln", "capacity": 8 },
  { "id": 4, "name": "Red Rocks", "capacity": 4 },
  { "id": 9, "name": "Kreuzberg", "capacity": 12 },
  { "id": 17, "name": "Flatirons", "capacity": 6 }
]
```

---

### 2. Create Single Booking (`POST /api/v1/bookings`)

Creates an individual meeting reservation.

```bash
curl -X POST http://localhost:8000/api/v1/bookings \
  -H "Content-Type: application/json" \
  -d '{
    "room_id": 3,
    "start": "2026-11-10T09:00:00",
    "end": "2026-11-10T10:00:00",
    "user": "alex"
  }'
```

**Response (`201 Created`)**:

```json
{
  "id": 1,
  "room_id": 3,
  "series_id": null,
  "user": "alex",
  "start": "2026-11-10T09:00:00",
  "end": "2026-11-10T10:00:00",
  "status": "active",
  "created_at_utc": "2026-10-21T18:00:00Z"
}
```

---

### 3. Create Recurring Booking (`POST /api/v1/bookings/recurring`)

Creates a weekly recurring series upfront, skipping up to 2 clashes under the 50% threshold rule.

```bash
curl -X POST http://localhost:8000/api/v1/bookings/recurring \
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
  "created": [...],
  "skipped": []
}
```

---

### 4. Cancel Single Booking (`DELETE /api/v1/bookings/{id}`)

Soft-deletes an individual standalone booking and immediately frees the time slot.

```bash
curl -X DELETE http://localhost:8000/api/v1/bookings/1
```

**Success Response (`200 OK`)**:

```json
{
  "id": 1,
  "status": "cancelled",
  "cancelled_at_utc": "2026-10-21T18:30:00Z"
}
```

**Series Rejection Response (`400 Bad Request`)**:
Attempting to delete an individual occurrence of a recurring series is rejected to protect series integrity. The entire series must be dissolved via `DELETE /api/v1/bookings/series/{series_id}`:

```json
{
  "detail": "Booking with id 2 belongs to recurring series 1. Individual series instances cannot be cancelled separately. Cancel the entire series via DELETE /api/v1/bookings/series/1 to cancel all future occurrences."
}
```

**Not Found Response (`404 Not Found`)**:

```json
{
  "detail": "Booking with id 999 not found"
}
```

---

### 5. Cancel Recurring Series (`DELETE /api/v1/bookings/series/{series_id}`)

Dissolves a recurring series, cancelling all future instances while preserving historical meetings.

```bash
curl -X DELETE http://localhost:8000/api/v1/bookings/series/1
```

**Response (`200 OK`)**:

```json
{
  "series_id": 1,
  "cancelled_count": 3,
  "kept_count": 1,
  "cancelled_at_utc": "2026-10-21T18:30:00Z"
}
```

---

### 6. System Health (`GET /health`)

Reports application status and live database pool connectivity.

```bash
curl -X GET http://localhost:8000/health
```

---

## Makefile Reference

| Command             | Action                                                        |
| ------------------- | ------------------------------------------------------------- |
| `make dev`          | Start development server on `localhost:8000`                  |
| `make start`        | Start production server (`ENVIRONMENT=production`)             |
| `make seed`         | Idempotently seed prototype rooms into SQLite                 |
| `make test`         | Run complete pytest test suite (`ENVIRONMENT=test`)           |
| `make test-v`       | Run pytest suite with verbose output                          |
| `make lint`         | Run Ruff linter checks across `src/` and `tests/`             |
| `make format`       | Auto-format codebase using Ruff                               |
| `make format-check` | Check code formatting compliance                              |
| `make verify`       | Run full quality gate: linter, format check, and all 92 tests |
| `make clean`        | Clean pycache, pytest caches, and temporary test databases    |

---

## Test Suite & Quality Gate

The test suite covers **92 automated tests** across 11 test modules:

```bash
$ make verify
uv run ruff check src tests
All checks passed!
uv run ruff format --check src tests
50 files already formatted
ENVIRONMENT=test uv run pytest
============================== 92 passed in 3.38s ==============================
```

### Risk Scenarios Tested

- **Denver Winter DST Transition**: Weekly recurrence across the 2026-11-01 Denver DST boundary retains `09:00:00` local time without hour drift.
- **Berlin Autumn DST Transition**: Weekly recurrence across the 2026-10-25 Berlin DST boundary retains `09:00:00` local time.
- **Spring-Forward DST Gaps**: Rejects non-existent local wall times (e.g., Berlin 02:30 on 2027-03-28) with `422`.
- **R1/R2 Conflict Thresholds**: 4-week series with 2 conflicts succeeds with 2 skipped (50% rule), while a 2-week series with 2 conflicts (0% success) or a series with 3 conflicts ($>2$) triggers an atomic rollback (`409`).
- **Series Cancellation & Historical Preservation**: Verifies future series instances are cancelled, past instances remain active, and cancelled slots are immediately bookable again.
- **Series Integrity**: Forbids cherry-picking individual series instances via `DELETE /api/v1/bookings/{id}`, requiring whole-series dissolution.
- **Contract C2 Integrity**: Verifies `GET /rooms` returns exact keys `{id, name, capacity}` for prototype IDs `3, 4, 9, 17`.
- **Strict API Versioning**: Confirms `/api/v1/bookings` is enforced while unversioned `GET /rooms` is isolated for legacy dashboard compatibility.
- **High Concurrency Serialization**: 8 simultaneous worker threads attempting to book the exact same slot result in exactly 1 success and 7 rejections without database corruption.
- **Immutable Audit Trail**: All 6 lifecycle events are verified in the `audit_logs` table.
