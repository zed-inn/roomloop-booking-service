# RoomLoop — Architecture & Engineering Decisions (`DECISIONS.md`)

This document records the architectural decisions, trade-offs, Product Manager questions, AI collaboration log, and future roadmap for the RoomLoop booking service.

---

## (a) Decisions Made Where the Brief Was Silent, and Why

1. **Reconciling R1 and R2 via the "50% + Max 2 Conflict" Policy**:
   - _Problem_: The brief presents an apparent contradiction: R1 states recurring bookings are "all-or-nothing", while R2 states that if "1 or 2 instances conflict, skip them and create the rest". Applying R2 to a 1-instance or 2-instance series where all slots conflict would result in creating zero rows.
   - _Decision_: A recurring request is accepted if and only if: (1) conflicts $C \le 2$, (2) created count $S \ge 0.5 \times N$, and (3) $S \ge 1$. Otherwise, an atomic rollback occurs (R1) returning 409 Conflict. This protects users from booking fragmented, unviable series while honoring R2.

2. **Room-Local Naive ISO Timestamp Storage (Contract C1 & OM-2)**:
   - _Problem_: Denver meetings drifted by 1 hour in winter (OM-2) when timestamps were stored or generated using UTC arithmetic.
   - _Decision_: Timestamps are stored as canonical naive ISO strings (`YYYY-MM-DDTHH:MM:SS`) in the room's local timezone. Weekly recurrence is calculated by adding 7 calendar days to the naive datetime rather than converting through UTC. This guarantees meetings always occur at `09:00:00` local wall-clock time across DST shifts in both Berlin and Denver.

3. **Rejection of Non-Existent Wall-Clock Times (DST Spring-Forward Gap)**:
   - _Problem_: Naive ISO strings can represent times that do not exist in reality (e.g., Berlin 02:30:00 on 2027-03-28 when clocks jump from 02:00 to 03:00).
   - _Decision_: Every start and end timestamp is verified against the room's `zoneinfo.ZoneInfo`. Any timestamp falling in a spring-forward gap is rejected with `422 Unprocessable Entity`. Fall-back ambiguous times are resolved deterministically using `fold=0`.

4. **Strict Isolation of Contract C2 (`GET /rooms`)**:
   - _Problem_: The dashboard team's consumer script expects `{id, name, capacity}` and "renders whatever comes back". Leaking internal columns could break third-party scrapers or UI layouts.
   - _Decision_: The `RoomResponse` schema strictly forbids extra fields (`ConfigDict(extra="forbid")`) and returns only `id`, `name`, and `capacity`. Metadata such as `timezone` and `is_active` remains internal to the service.

5. **Refutation of the R5 Sequential Assumption**:
   - _Problem_: R5 suggested room IDs iterate `1..N`, but Contract C2 proved prototype IDs are non-sequential (`[3, 4, 9, 17]`).
   - _Decision_: The repository queries active room IDs dynamically and returns `404 Not Found` for missing rooms (`1, 2, 5..8`), treating room IDs as arbitrary primary keys rather than contiguous indices.

6. **Room-Local Timezone Cutoff for Series Cancellation (OM-1)**:
   - _Problem_: The office manager needed to dissolve abandoned series easily, but cancelling a series must leave past instances intact for nightly reporting (C1).
   - _Decision_: `DELETE /series/{id}` evaluates the cutoff timestamp in the room's local timezone. Meetings that have already started or concluded are preserved as `status="active"`, while future meetings are marked `status="cancelled"`, immediately freeing those slots for other teams.

7. **Eager Concurrency Write Locking (`BEGIN IMMEDIATE`)**:
   - _Problem_: SQLite default `DEFERRED` transactions allow multiple concurrent requests to read the same free slot simultaneously before attempting to write, causing race conditions and double bookings.
   - _Decision_: Configured SQLite Write-Ahead Logging (`WAL`) and hooked a `BEGIN IMMEDIATE` event listener into the SQLAlchemy engine. Write locks are acquired eagerly before conflict queries execute, serializing concurrent bookings at the database level without race conditions.

8. **Dual-Layer Logging (Application Stream + Immutable Audit Table)**:
   - _Problem_: Diagnosing recurring conflicts, rejected series, and cancellations requires verifiable history.
   - _Decision_: Implemented real-time structured logging via `RoomLoop` logger alongside an immutable SQLite `audit_logs` table recording all state transitions (`BOOKING_CREATED`, `SERIES_CREATED`, `CONFLICT_SKIPPED`, `SERIES_ROLLED_BACK`, `BOOKING_CANCELLED`, `SERIES_CANCELLED`).

9. **52-Week Maximum Recurrence Horizon**:
   - _Problem_: The brief did not specify an upper bound on `repeat_until`, risking denial-of-service via series requests spanning decades.
   - _Decision_: Enforced a 52-week (1 year) maximum limit from `start`, rejecting larger horizons with `422 Unprocessable Entity`.

10. **REST API Chosen over CLI Interface**:
    - _Problem_: The brief allowed building either a REST API or CLI application and required a brief justification.
    - _Decision_: Contract C2 explicitly requires supporting the facilities dashboard, which already queries `GET /rooms` over HTTP. A CLI cannot service external HTTP requests or provide concurrent dashboard integrations. FastAPI was selected for native OpenAPI documentation, Pydantic v2 boundary validation, and async ASGI performance.

---

## (b) Questions to Ask the Product Manager Before Shipping

1. **Room Inventory vs. Bookable Catalog (The R5/C2 Gap)**:
   - Does `GET /rooms` reflect the entire company facility inventory, or only currently active, bookable spaces (explaining why IDs 1, 2, 5..8 are missing)? Should we introduce an administrative API for facilities to mark rooms offline for maintenance?

2. **Nightly Reporting Timezone Expectations**:
   - Contract C1 specifies naive local ISO timestamps. Does the downstream reporting job expect timestamps in each room's local timezone, or normalized to headquarters time (Berlin)?

3. **Recurrence Frequency Flexibility**:
   - Currently, recurrence is strictly weekly (every 7 calendar days). Do users require bi-weekly, monthly, or custom multi-day schedules (e.g., every Tuesday and Thursday) in the next release?

4. **In-Progress Meeting Cancellation Behavior**:
   - If an office manager cancels a recurring series while an instance is currently underway, should the ongoing meeting be terminated immediately or preserved until completion (as currently implemented)?

5. **Series Conflict Policy Customization**:
   - Is the "50% + max 2 conflicts" rule appropriate across all room tiers, or should executive/boardroom spaces require a strict 100% all-or-nothing policy?

6. **Data Retention & Soft-Deletion Lifecycle**:
   - How long should cancelled bookings and immutable audit records be retained in SQLite before archival or purging under GDPR and corporate data compliance policies?

7. **Series Booking Max Horizon**:
   - Is the 52-week recurrence cap aligned with company calendar policies, or should it be configurable per office location?

---

## (c) Where AI Helped and What It Got Wrong That Was Corrected

1. **Where AI Helped: Clean Architecture Scaffolding**:
   - AI rapidly scaffolded the class-based Clean Architecture mirroring Kartikey's production TypeScript layout, creating clean boundaries between DTO contracts, ORM models, repositories, and services.

2. **Where AI Helped: DST Transition Fixture Generation**:
   - AI accurately identified the specific 2026/2027 DST change dates for Berlin (`2026-10-25`) and Denver (`2026-11-01`), saving time researching historical timezone schedules.

3. **Correction: Stale Package Version Metadata**:
   - _What AI Got Wrong_: AI web search summaries claimed outdated library versions (FastAPI 0.143.0).
   - _Correction_: Verified directly against live PyPI feeds and configured modern versions (FastAPI 0.156.1, SQLAlchemy 2.1.5, Pydantic 2.14.1).

4. **Correction: SQLite Re-entrant Session Deadlock**:
   - _What AI Got Wrong_: In the initial cancellation implementation, AI opened a second database connection inside an active `BEGIN IMMEDIATE` transaction to lookup the room's timezone. Because SQLite allows only one writer at a time, the second connection deadlocked waiting for the first connection's lock to release.
   - _Correction_: Refactored `RoomRepository.get_by_id(room_id, session=None)` to accept and reuse the active session, eliminating the self-deadlock.

5. **Correction: Audit Trail Rollback Contamination**:
   - _What AI Got Wrong_: When a recurring series was rejected for exceeding conflict thresholds, AI raised `HTTPException(409)` inside the active transaction, which inadvertently rolled back the `SERIES_ROLLED_BACK` audit record along with the bookings.
   - _Correction_: Refactored the service to explicitly rollback the booking session first, then commit the `SERIES_ROLLED_BACK` audit record in an independent transaction.

6. **Correction: Argon's Flawed Conflict Rule**:
   - _What AI Got Wrong_: External competitor analysis (Argon) suggested blindly skipping up to 2 conflicts without checking minimum success rate, creating 0 bookings for 2-instance series.
   - _Correction_: Formulated and implemented the 50% threshold formula ensuring at least 1 booking succeeds and at least 50% of the series is created.

7. **Correction: Missing Spring-Forward DST Gap Validation**:
   - _What AI Got Wrong_: AI initially performed naive date arithmetic that allowed non-existent local times (e.g. 02:30 during Berlin spring-forward).
   - _Correction_: Implemented `validate_local_wall_time` using `zoneinfo` fold comparisons to reject non-existent times with 422.

---

## (d) Deliberate Omissions and What to Build Next

1. **Deliberate Omission: User Authentication & Role-Based Access Control (RBAC)**:
   - _Rationale_: The brief requested an internal core booking service without specifying authentication requirements. Adding mock JWT/session tokens would introduce unnecessary complexity and could break third-party dashboard scrapers.
   - _What to Build Next_: Integrate OpenID Connect (OIDC) / Google Workspace OAuth2 to enforce role-based permissions (e.g., standard users vs. facilities managers).

2. **Deliberate Omission: Distributed Database (PostgreSQL)**:
   - _Rationale_: SQLite Write-Ahead Logging (`WAL`) with `BEGIN IMMEDIATE` provides complete ACID transactions and concurrency guarantees for single-instance deployments without requiring external Docker or cloud database setup.
   - _What to Build Next_: Provide a PostgreSQL database adapter utilizing `SELECT ... FOR UPDATE` row-level locks to support horizontal scaling across multi-node Kubernetes deployments.

3. **Deliberate Omission: Granular Series Modification**:
   - _Rationale_: Editing individual occurrences of an active series (e.g., moving next Tuesday's meeting to 10:00) introduces split-series edge cases beyond the brief's scope.
   - _What to Build Next_: Implement single-instance rescheduling and exception tracking within a series parent entity.

4. **What to Build Next: Real-Time Calendar Sync & Webhooks**:
   - Dispatch outgoing webhooks or integrate with Google Calendar / Microsoft Outlook APIs to automatically sync room bookings with employees' corporate calendars.

5. **What to Build Next: Room Amenities & Capacity Filtering**:
   - Add query parameters to `GET /rooms` (e.g., `?min_capacity=10&has_video_conference=true`) allowing users to filter rooms by equipment and physical capabilities.
