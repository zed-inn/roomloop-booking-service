from datetime import datetime, timedelta, timezone
from fastapi import HTTPException

from roomloop.config.database import DatabaseConnection
from roomloop.modules.audit.repository import AuditLogRepository
from roomloop.modules.bookings.contract import (
    BookingCreateRequest,
    BookingResponse,
    RecurringBookingCreateRequest,
    RecurringBookingResponse,
    SkippedInstance,
)
from roomloop.modules.bookings.model import BookingModel, SeriesModel
from roomloop.modules.bookings.repository import BookingRepository
from roomloop.modules.rooms.repository import RoomRepository
from roomloop.shared.utils.time import (
    TimeValidationError,
    format_naive_iso,
    generate_weekly_occurrences,
    parse_naive_iso,
    validate_local_wall_time,
)


class BookingService:
    """business service coordinating single/recurring bookings, conflict policies, and audit logging"""

    def __init__(
        self,
        db: DatabaseConnection,
        booking_repo: BookingRepository,
        room_repo: RoomRepository,
        audit_repo: AuditLogRepository,
    ) -> None:
        self.db = db
        self.booking_repo = booking_repo
        self.room_repo = room_repo
        self.audit_repo = audit_repo

    def create_single_booking(
        self, request: BookingCreateRequest
    ) -> BookingResponse:
        """creates single meeting booking ensuring room existence, dst validity, and zero overlap"""
        # room existence verification
        room = self.room_repo.get_by_id(request.room_id)
        if room is None:
            raise HTTPException(
                status_code=404,
                detail=f"Room with id {request.room_id} not found",
            )

        # parse and validate timestamps
        try:
            start_dt = parse_naive_iso(request.start)
            end_dt = parse_naive_iso(request.end)
            if end_dt <= start_dt:
                raise TimeValidationError(
                    "end datetime must be strictly after start datetime"
                )
            if end_dt - start_dt >= timedelta(days=7):
                raise TimeValidationError(
                    "single meeting duration must be less than 7 days"
                )
            validate_local_wall_time(start_dt, room.timezone)
            validate_local_wall_time(end_dt, room.timezone)
        except TimeValidationError as err:
            raise HTTPException(status_code=422, detail=str(err))

        now_utc = datetime.now(timezone.utc).isoformat()

        # execute within immediate write transaction
        with self.db.get_session() as session:
            with session.begin():
                conflicts = self.booking_repo.find_conflicts(
                    session, request.room_id, request.start, request.end
                )
                if conflicts:
                    raise HTTPException(
                        status_code=409,
                        detail=(
                            f"Conflict detected with booking {conflicts[0].id} "
                            f"({conflicts[0].start_local} - {conflicts[0].end_local})"
                        ),
                    )

                booking = BookingModel(
                    room_id=request.room_id,
                    series_id=None,
                    user_name=request.user.strip(),
                    start_local=request.start,
                    end_local=request.end,
                    status="active",
                    created_at_utc=now_utc,
                )
                self.booking_repo.create_booking(session, booking)

                # append immutable audit log record
                self.audit_repo.record_event(
                    session=session,
                    event_type="BOOKING_CREATED",
                    entity_type="booking",
                    entity_id=booking.id,
                    user_name=booking.user_name,
                    details={
                        "room_id": booking.room_id,
                        "start": booking.start_local,
                        "end": booking.end_local,
                    },
                    now_utc=now_utc,
                )

        return BookingResponse(
            id=booking.id,
            room_id=booking.room_id,
            series_id=None,
            user=booking.user_name,
            start=booking.start_local,
            end=booking.end_local,
            status="active",
            created_at_utc=booking.created_at_utc,
        )

    def create_recurring_booking(
        self, request: RecurringBookingCreateRequest
    ) -> RecurringBookingResponse:
        """creates recurring series upfront applying the 50% + max 2 conflict threshold rule"""
        room = self.room_repo.get_by_id(request.room_id)
        if room is None:
            raise HTTPException(
                status_code=404,
                detail=f"Room with id {request.room_id} not found",
            )

        try:
            start_dt = parse_naive_iso(request.start)
            end_dt = parse_naive_iso(request.end)
            if request.repeat_until > start_dt.date() + timedelta(days=366):
                raise TimeValidationError(
                    "repeat_until exceeds 52 weeks maximum allowed limit"
                )
            occurrences = generate_weekly_occurrences(
                start_dt=start_dt,
                end_dt=end_dt,
                repeat_until=request.repeat_until,
                tz_name=room.timezone,
            )
        except TimeValidationError as err:
            raise HTTPException(status_code=422, detail=str(err))

        total_requested = len(occurrences)
        now_utc = datetime.now(timezone.utc).isoformat()

        with self.db.get_session() as session:
            with session.begin():
                valid_slots: list[tuple[str, str]] = []
                skipped_slots: list[SkippedInstance] = []

                for occ_start, occ_end in occurrences:
                    occ_start_str = format_naive_iso(occ_start)
                    occ_end_str = format_naive_iso(occ_end)
                    clashes = self.booking_repo.find_conflicts(
                        session, request.room_id, occ_start_str, occ_end_str
                    )
                    if clashes:
                        skipped_slots.append(
                            SkippedInstance(
                                start=occ_start_str,
                                end=occ_end_str,
                                reason=f"Clash with existing booking {clashes[0].id}",
                            )
                        )
                    else:
                        valid_slots.append((occ_start_str, occ_end_str))

                conflicts_count = len(skipped_slots)
                created_count = len(valid_slots)

                # evaluate 50% rule + max 2 conflicts rule (reconciling r1 and r2)
                is_eligible = (
                    conflicts_count <= 2
                    and created_count >= (0.5 * total_requested)
                    and created_count >= 1
                )

                if not is_eligible:
                    # rollback booking session
                    session.rollback()

                    # persist audit log event for the rejected series attempt
                    with self.db.get_session() as audit_session:
                        with audit_session.begin():
                            self.audit_repo.record_event(
                                session=audit_session,
                                event_type="SERIES_ROLLED_BACK",
                                entity_type="series",
                                entity_id=None,
                                user_name=request.user.strip(),
                                details={
                                    "room_id": request.room_id,
                                    "total_requested": total_requested,
                                    "conflicts_count": conflicts_count,
                                    "created_count": created_count,
                                },
                                now_utc=now_utc,
                            )
                    raise HTTPException(
                        status_code=409,
                        detail=(
                            f"Recurring booking rejected: {conflicts_count} conflicts exceed threshold "
                            f"(max 2 allowed, at least 50% must succeed, got {created_count}/{total_requested})"
                        ),
                    )

                # create recurring series parent record
                series = SeriesModel(
                    room_id=request.room_id,
                    user_name=request.user.strip(),
                    repeat_until=request.repeat_until.isoformat(),
                    created_at_utc=now_utc,
                )
                self.booking_repo.create_series(session, series)

                created_responses: list[BookingResponse] = []
                for start_str, end_str in valid_slots:
                    booking = BookingModel(
                        room_id=request.room_id,
                        series_id=series.id,
                        user_name=request.user.strip(),
                        start_local=start_str,
                        end_local=end_str,
                        status="active",
                        created_at_utc=now_utc,
                    )
                    self.booking_repo.create_booking(session, booking)
                    created_responses.append(
                        BookingResponse(
                            id=booking.id,
                            room_id=booking.room_id,
                            series_id=series.id,
                            user=booking.user_name,
                            start=booking.start_local,
                            end=booking.end_local,
                            status="active",
                            created_at_utc=now_utc,
                        )
                    )

                # log audit trail for successful series creation
                self.audit_repo.record_event(
                    session=session,
                    event_type="SERIES_CREATED",
                    entity_type="series",
                    entity_id=series.id,
                    user_name=series.user_name,
                    details={
                        "total_requested": total_requested,
                        "created_count": created_count,
                        "skipped_count": conflicts_count,
                    },
                    now_utc=now_utc,
                )

                # log audit trail for individual skipped conflict instances
                for skipped in skipped_slots:
                    self.audit_repo.record_event(
                        session=session,
                        event_type="CONFLICT_SKIPPED",
                        entity_type="series",
                        entity_id=series.id,
                        user_name=series.user_name,
                        details={
                            "start": skipped.start,
                            "end": skipped.end,
                            "reason": skipped.reason,
                        },
                        now_utc=now_utc,
                    )

        return RecurringBookingResponse(
            series_id=series.id,
            total_requested=total_requested,
            created_count=created_count,
            skipped_count=conflicts_count,
            created=created_responses,
            skipped=skipped_slots,
        )
