# RoomLoop — Engineering & Architectural Decisions (`DECISIONS.md`)

This document details the architectural decisions, trade-offs, Product Manager questions, AI collaboration audit, and future roadmap for the RoomLoop booking service.

---

## (a) Decisions Made Where the Brief Did Not Tell You What to Do, and Why

### 1. REST API Chosen Over CLI Application
- **The Brief Said**: *"You may build this as a small REST API or a CLI application — your call. Briefly justify the choice."*
- **Our Decision**: Built as a FastAPI REST API.
- **Why**: Integration constraint C2 explicitly requires serving the facilities dashboard (`GET /rooms`) over HTTP, and internal tools already consume the API. A CLI cannot serve web dashboards, handle concurrent employee requests, or expose interactive OpenAPI documentation.

### 2. Reconciling R1 and R2 via the "50% Success + Max 2 Conflicts" Rule
- **The Problem**: Rule R1 states recurring bookings are all-or-nothing (if it cannot be fully created, nothing is saved). Rule R2 states that if 1 or 2 instances conflict, skip just those and create the rest. The brief is silent on edge cases: if a user requests a 1- or 2-week series and all slots clash, blindly applying R2 would create 0 bookings while returning a misleading "201 Created".
- **Our Decision**: A series is accepted if and only if:
  1. Conflicts $C \le 2$ (satisfies R2).
  2. Successfully created instances $S \ge 0.5 \times N$ (at least 50% of the series succeeds).
  3. At least 1 booking is created ($S \ge 1$).
  If these conditions are not met, Rule R1 triggers: the entire transaction rolls back atomically returning `409 Conflict`.
- **Decision Matrix**:
  | Total $N$ | Conflicts $C$ | Created $S$ | Success Rate ($S/N$) | Status Code | Outcome / Reason |
  | :---: | :---: | :---: | :---: | :---: | :--- |
  | 1 | 0 | 1 | 100% | `201 Created` | Full series creation |
  | 1 | 1 | 0 | 0% | `409 Conflict` | 0% success (zero bookings created) |
  | 2 | 1 | 1 | 50% | `201 Created` | $C \le 2$ AND $50\% \ge 50\%$ |
  | 2 | 2 | 0 | 0% | `409 Conflict` | 0% success (all instances clash) |
  | 3 | 2 | 1 | 33.3% | `409 Conflict` | $33.3\% < 50\%$ threshold |
  | 4 | 2 | 2 | 50% | `201 Created` | $C \le 2$ AND $50\% \ge 50\%$ |
  | 6 | 2 | 4 | 66.7% | `201 Created` | $C \le 2$ AND $66.7\% \ge 50\%$ |
  | 10 | 3 | 7 | 70% | `409 Conflict` | $C = 3 > 2$ (violates max 2 conflicts) |

### 3. Room-Local Naive ISO Timestamps to Fix Denver Winter Drift (R3, C1, OM-2)
- **The Problem**: The Office Manager reported: *"Also half of Denver’s bookings last winter showed up an hour off, no one ever figured out why."*
- **Root Cause Hypotheses**:
  - *Hypothesis 1 (UTC math drift)*: The prototype converted local times to UTC and added 7 days in seconds ($7 \times 86400$). Because Berlin changes DST on the last Sunday of October (e.g. 2026-10-25) while Denver changes DST on the first Sunday of November (e.g. 2026-11-01), the time difference between Berlin and Denver temporarily shifts from 8 hours to 7 hours.
  - *Hypothesis 2 (Fixed offset capture)*: The prototype captured a fixed UTC offset at creation time (e.g. UTC-6 in summer) and applied it across winter (when Denver is UTC-7), causing all summer-created winter meetings ("half" the bookings) to drift by 1 hour.
- **Our Decision**: Stored all timestamps as naive local ISO strings (`YYYY-MM-DDTHH:MM:SS`) in the room's timezone, satisfying Contract C1 for nightly reporting. Weekly recurrence advances by 7 calendar days directly on the local wall-clock date (`current_start + timedelta(days=7)`).
- **Why**: A 09:00 AM meeting in Denver remains at 09:00 AM local wall-clock time year-round across all DST boundaries, permanently eliminating the 1-hour winter shift.

### 4. Handling Spring-Forward DST Gaps & Fall-Back Folds
- **The Problem**: When clocks jump forward in spring (e.g., Europe/Berlin jumps from 02:00 to 03:00 on 2027-03-28), the local time `02:30:00` does not physically exist. Accepting it causes downstream calendar errors.
- **Our Decision**: Every submitted timestamp is validated against the room's `zoneinfo.ZoneInfo`. Non-existent spring-forward gap times return `422 Unprocessable Entity`. Ambiguous autumn fall-back times default deterministically to `fold=0`.

### 5. Series Cancellation vs. Single Cancellation (OM-1, C1)
- **The Problem**: The Office Manager noted: *"Biggest complaint is people booking a room every Monday for 6 months and then the team dissolves and the room sits ‘busy’ forever. Whatever you build, please make sure someone can actually get rid of a whole series easily."*
- **Our Decision**:
  - Implemented `DELETE /api/v1/bookings/series/{id}`, evaluating current time in the room's timezone: future instances are soft-deleted (`status="cancelled"`, `cancelled_at_utc`), immediately freeing the room, while past and in-progress meetings remain `active` for Contract C1 reporting.
  - The conflict check query filters strictly on `WHERE status = 'active'`, ensuring cancelled slots are immediately bookable again.
  - Attempting to delete an individual occurrence of a recurring series via `DELETE /api/v1/bookings/{id}` returns `400 Bad Request` to preserve series integrity.
  - "Someone can get rid of a whole series": Cancellation does not require original booker authentication, ensuring abandoned series can be cleared when employees leave or teams dissolve.

### 6. Dynamic Room Discovery Over Contiguous 1..N Iteration (R5 vs. C2)
- **The Problem**: Requirement R5 states rooms can be iterated 1 to N, but integration constraint C2 provided actual sample room IDs with non-sequential gaps (`[3, 4, 9, 17]`).
- **Our Decision**: Treated room IDs as arbitrary database primary keys queried dynamically. Requests for unallocated room IDs (1, 2, 5..8) return `404 Not Found`.
- **Why**: Real-world facilities expand, decommission, and renumber rooms over time; assuming contiguous sequences causes crashes or false availability.

### 7. Concurrency Protection via `BEGIN IMMEDIATE` and SQLite WAL Mode (R4)
- **The Problem**: In SQLite, transactions default to `DEFERRED`, meaning exclusive write locks are acquired only on write. Two concurrent requests checking availability simultaneously would both see a slot as free, causing double bookings.
- **Our Decision**: Enabled Write-Ahead Logging (`PRAGMA journal_mode=WAL`) for concurrent readers and registered an engine listener executing `BEGIN IMMEDIATE` at the start of every transaction to acquire an exclusive write lock before checking overlaps.
- **Why**: Guarantees serializable isolation under concurrent booking attempts. Tested with 8 simultaneous threads competing for the same slot: exactly 1 succeeds, 7 fail with `409 Conflict`.

### 8. Strict Fixed-Width Canonical ISO Storage for Lexicographical SQL Indexing
- **The Problem**: Comparing timestamps in SQL queries (`start_local < :end AND end_local > :start`) requires string comparisons to match chronological order.
- **Our Decision**: Enforced strict 19-character ISO format (`YYYY-MM-DDTHH:MM:SS`) via Pydantic validators and database check constraints.
- **Why**: Guarantees that SQLite's native index string comparisons (`<`, `<=`, `>`, `>=`) behave identically to datetime comparisons without conversion overhead.

### 9. Decoupling Database Seeding from Server Boot
- **The Problem**: Automatically populating prototype data on server boot risks mutating or duplicating state across deployments.
- **Our Decision**: Decoupled room seeding into an explicit CLI command (`make seed`), while server startup checks schema readiness and logs a reminder if rooms are unseeded.
- **Why**: Adheres to standard 12-factor application lifecycle practices.

### 10. Dual-Layer Observability (Asynchronous Queue Logging + Audit Table)
- **The Problem**: Synchronous stdout logging blocks the async request loop under load. Real-time console logs can also be lost upon container restart.
- **Our Decision**: Standardized on Python standard `QueueHandler` and `QueueListener` running on a background worker thread for non-blocking console logging, coupled with an append-only `audit_logs` SQLite table recording all booking creations, skips, rollbacks, and cancellations.
- **Why**: Zero I/O blocking for HTTP handlers, plus an immutable audit trail for conflict diagnosis.

### 11. Internal API Usability (CORS, Distributed Tracing, Health Probes)
- **The Problem**: The brief noted that other internal tools consume the API.
- **Our Decision**: Added `CORSMiddleware` (allowing internal web portals on different ports to query the API), `RequestLoggingMiddleware` with `X-Request-ID` correlation tracing, and a `/health` endpoint for internal orchestrator readiness probes.
- **Why**: Allows any internal dashboard, script, or microservice to integrate with zero friction.

### 12. High-Concurrency Concurrency Tuning & Load Testing Architecture
- **The Problem**: Under high-volume concurrent traffic (10k, 100k, 1M requests), SQLite's default disk synchronization (`PRAGMA synchronous = FULL`) forces a disk `fsync` on every intermediate write transaction, capping write throughput to ~50 writes/second and triggering `database is locked` operational timeouts across worker threads.
- **Our Decision**:
  - Configured `PRAGMA synchronous = NORMAL` in Write-Ahead Logging mode (`WAL`), guaranteeing zero database corruption on crash while eliminating per-transaction fsync stalls.
  - Set `PRAGMA busy_timeout = 5000` to allow worker threads to retry lock acquisition for up to 5,000ms during burst writes rather than throwing immediate errors.
  - Allocated a 64 MB in-memory page cache (`PRAGMA cache_size = -64000`) for high-speed indexing.
  - Built a 5,000-request payload bank (`tests/load/payloads.json` via `generate_payloads.py`) evaluating dynamic placeholders (`##...`) across a 4-year timestamp window (2025–2028), DST gap edge cases, invalid IDs (404), validation rejections (422), and forbidden fields.
  - Built an automated markdown report generator exporting `tests/load/LOAD_TEST_RESULTS.md` directly from k6 on every run.
- **Why**: Proves empirically that RoomLoop reliably sustains high multi-user concurrent traffic with an error budget of **0.00% 5xx server errors**.

### 13. Exclusive Conference Room Tenancy vs. Capacity Semantics (Rule R4 vs. Contract C2)
- **The Problem**: Contract C2 returns `{"id": int, "name": str, "capacity": int}`, which raises the question: does `capacity` allow multiple independent bookings to share a room concurrently up to that limit, or is every booking an exclusive reservation of the entire room?
- **Our Decision**:
  - We strictly enforce **exclusive single-booking room occupancy** per PM Requirement R4:
    > *"R4. Two bookings conflict if they overlap in time in the same room. Back-to-back bookings (one ends 10:00, the next starts 10:00) are not a conflict."*
  - A meeting room is an enclosed private space for team collaboration, client calls, and confidential discussions. Even if Room 3 ("Aurora", capacity 8) is booked by a team of 3, other teams cannot simultaneously book the room.
  - `capacity` in Contract C2 functions as informational facilities metadata informing employees of maximum physical seating so they can select an appropriately sized room.

---

## (b) Questions to Ask the Product Manager Before Shipping

1. **Room Inventory & Missing IDs in Contract C2**:
   - Why are room IDs 1, 2, and 5 through 8 absent from C2? Are they non-meeting utility spaces (phone booths, cafeteria, server room), or rooms temporarily offline for maintenance? Should the API support an `is_active` or maintenance status filter?

2. **Nightly Reporting Timezone Assumptions (Contract C1)**:
   - Contract C1 states reporting parses naive local ISO strings. Does the reporting script assume all timestamps represent company HQ time (Berlin), or does it understand each room's local timezone (Berlin vs. Denver)?

3. **In-Progress Meeting Cancellation (OM-1)**:
   - When an Office Manager dissolves a series while a meeting is underway, should the ongoing meeting continue normally (as currently implemented to protect reporting), or be terminated immediately to free the room for ad-hoc use?

4. **Single-Instance Cancellation for Holidays**:
   - Currently, deleting an individual occurrence of a recurring series returns `400 Bad Request` to preserve series integrity. In the future, should employees be allowed to skip a single occurrence (e.g., for a public holiday) without cancelling the entire series?

5. **Meeting Duration Bounds & Slot Snapping**:
   - Does company policy require enforcing minimum meeting lengths (e.g., 15 or 30 minutes) and snapping bookings to standard clock intervals (:00, :15, :30, :45) to avoid calendar fragmentation?

6. **Maximum Recurrence Horizon**:
   - We capped recurrence at 52 weeks (1 year) to prevent unbounded loops. Is 52 weeks appropriate, or should recurrence be restricted to quarterly (12 weeks) or semesterly (26 weeks) booking windows?

7. **Room Capacity Semantics — Physical Sizing vs. Booking Utilization**:
   - What exactly is `capacity` in Contract C2, or did we understand it correctly?
   - In our implementation, `capacity` is treated strictly as physical room seating metadata (number of chairs/tables) for the Facilities Dashboard, while each booking represents an exclusive reservation of the entire room (per Rule R4: *"Two bookings conflict if they overlap in time in the same room"*).
   - Did we understand this correctly, or is there an expectation for headcount validation (e.g., adding an optional `attendees: int` to booking requests and rejecting if `attendees > room.capacity`)?
   - Furthermore, could `capacity` ever imply shared hot-desking/seat allocation (where multiple independent users book slots in the same room up to capacity), or should meeting rooms always remain exclusive single-booking spaces?

---

## (c) Where AI Helped, and What It Got Wrong That Was Corrected

### Where AI Helped
1. **Timezone Transition Dates**: AI accurately identified the specific DST transition dates for Berlin (`2026-10-25`) and Denver (`2026-11-01`), accelerating test fixture setup.
2. **Interval Boundary Test Scenarios**: AI helped quickly generate boundary test parameter matrices for overlapping, touching, and back-to-back intervals.

### What AI Got Wrong and How I Corrected It
1. **Hallucinated a 24-Hour Meeting Limit**:
   - *AI Error*: AI hallucinated that "meetings cannot exceed 24 hours" and attempted to reject all multi-day bookings.
   - *Correction*: Multi-day workshops (< 7 days) are completely valid. The actual issue was that recurrence validation did not verify `repeat_until >= end_dt.date()`. I corrected the boundary check so multi-day meetings succeed whenever `repeat_until` accommodates the meeting's conclusion date.
2. **Permitted Cherry-Picking Recurring Series Instances**:
   - *AI Error*: AI naively allowed `DELETE /bookings/{id}` to soft-delete single occurrences of a recurring series without validation.
   - *Correction*: Added a check in `cancel_single_booking` rejecting series bookings with `400 Bad Request`. A recurring series must be cancelled via `DELETE /api/v1/bookings/series/{id}`, satisfying OM-1 and preserving series integrity.
3. **SQLite Re-Entrant Lock Deadlock**:
   - *AI Error*: In the initial cancellation implementation, AI opened a secondary database connection inside an active `BEGIN IMMEDIATE` transaction to lookup the room's timezone, causing SQLite to hang indefinitely.
   - *Correction*: Refactored `RoomRepository.get_by_id` to accept and reuse the active database session.
4. **Audit Trail Rollback Contamination**:
   - *AI Error*: When a series exceeded conflict thresholds, AI raised an HTTP 409 exception inside the active database session, accidentally rolling back the `SERIES_ROLLED_BACK` audit record along with the rejected bookings.
   - *Correction*: Refactored the service to explicitly rollback the booking session first, then commit the audit record in an independent transaction.
5. **Flawed Conflict Skipping Logic (Empty Series Creation)**:
   - *AI Error*: AI proposed a naive interpretation of Rule R2 that blindly skipped up to 2 conflicts without checking the overall series success rate. A 2-instance series with 2 conflicts would skip both and create 0 bookings while returning success.
   - *Correction*: Formulated and implemented the 50% threshold formula ensuring at least 1 booking succeeds and at least 50% of the series is created.
6. **Ignored Spring-Forward DST Gaps**:
   - *AI Error*: AI used naive date math that allowed non-existent local times (e.g., 02:30 during the Berlin spring-forward transition).
   - *Correction*: Added `validate_local_wall_time` using `zoneinfo` fold checks to reject non-existent clock times with `422 Unprocessable Entity`.
7. **Stale Library Versions**:
   - *AI Error*: AI web summaries suggested outdated package versions (e.g., FastAPI 0.143).
   - *Correction*: Verified all dependencies directly against PyPI (FastAPI 0.156.1, SQLAlchemy 2.1.5, Pydantic 2.14.1).
8. **Static Load Testing Payloads & Missing SQLite WAL Synchronization Tuning**:
   - *AI Error*: When asked to implement load testing, AI initially generated a simple script with static, hardcoded timestamps on a single day. This artificially caused almost 100% conflicts on writes, tested zero DST transition edge cases, and omitted SQLite `PRAGMA synchronous = NORMAL` and `busy_timeout` tuning, resulting in lock contention timeouts under 30 concurrent virtual users.
   - *Correction*: Engineered a 5,000-request payload bank across a 4-year window with runtime placeholder evaluators (`##...`) testing valid reservations, non-existent room IDs (404), Berlin spring-forward gap hours (422), inverted intervals (422), and forbidden extra fields (422). Tuned SQLite with `PRAGMA journal_mode = WAL`, `PRAGMA synchronous = NORMAL`, and `PRAGMA busy_timeout = 5000`, achieving 100.00% contract compliance and 0.00% 5xx server errors across 10,000 concurrent requests.
9. **Conflating Conference Room Capacity with Shared Multi-Tenant Hot-Desking**:
   - *AI / Design Misconception*: A developer or AI might wonder why `capacity` (e.g., capacity 8 for room 3) does not allow 8 separate overlapping bookings at the same time.
   - *Correction & Domain Clarity*: Verified against PM Requirement R4 (*"Two bookings conflict if they overlap in time in the same room"*). Meeting rooms are exclusive physical assets: two unrelated teams cannot hold separate meetings in the same room simultaneously without destroying meeting privacy and acoustics. Clarified the domain boundary between exclusive meeting rooms and shared hot-desks, and framed the exact clarifying question for the PM regarding whether optional `attendees` headcount validation should be introduced.

---

## (d) Anything Deliberately Left Out, and What to Build Next

### Deliberately Left Out for This Scope
1. **User Authentication & Role-Based Access Control (RBAC)**:
   - *Why*: The brief specified `user: str` in payloads and asked for an internal booking core for ~200 employees. Adding mock authentication would add friction and break existing prototype callers.
2. **Complex Recurrence Rules (RRULE / iCalendar)**:
   - *Why*: The brief strictly specified weekly recurrence (every 7 calendar days). Implementing bi-weekly, monthly, or arbitrary weekday rules was out of scope.
3. **External Distributed Queues & Message Brokers (RabbitMQ / Celery)**:
   - *Why*: For ~200 employees and 4 prototype rooms, SQLite with WAL mode and `BEGIN IMMEDIATE` provides complete ACID guarantees with sub-millisecond latencies and zero operational overhead. External distributed brokers would add infrastructure failure points without tangible benefit.

### What to Build Next (Internal API Focus)
1. **Internal SSO & Corporate Calendar Sync (Google Workspace / Outlook)**:
   - Connect the `user` string to internal Google Workspace or Microsoft 365 OAuth2, automatically dispatching calendar invites (`.ics`) to attendees when a room is booked.
2. **Granular Series Holiday Exception Handling (`EXDATE`)**:
   - Allow internal employees to skip or reschedule a single meeting occurrence for a company holiday without cancelling the entire recurring series.
3. **Internal Room Facilities & Equipment Search**:
   - Add query filters to `GET /rooms` (e.g., `?min_capacity=8&has_video=true`) so internal dashboards can display equipment and help teams find suitable rooms.
4. **Slack Notifications for Booking & Cancellation**:
   - Send automated confirmations and cancellation notices to internal team Slack channels (addressing the Office Manager's workflow).
