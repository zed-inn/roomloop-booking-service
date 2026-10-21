from fastapi import APIRouter

from roomloop.config.database import DatabaseConnection
from roomloop.modules.audit.repository import AuditLogRepository
from roomloop.modules.bookings.contract import (
    BookingCreateRequest,
    BookingResponse,
    CancelBookingResponse,
    CancelSeriesResponse,
    RecurringBookingCreateRequest,
    RecurringBookingResponse,
)
from roomloop.modules.bookings.controller import BookingController
from roomloop.modules.bookings.repository import BookingRepository
from roomloop.modules.bookings.service import BookingService
from roomloop.modules.rooms.repository import RoomRepository


def _assemble_controller(db: DatabaseConnection) -> BookingController:
    """helper assembling repository and service dependencies for booking controller"""
    booking_repo = BookingRepository()
    room_repo = RoomRepository(db)
    audit_repo = AuditLogRepository(db)
    booking_service = BookingService(
        db=db,
        booking_repo=booking_repo,
        room_repo=room_repo,
        audit_repo=audit_repo,
    )
    return BookingController(booking_service)


def create_bookings_router(db: DatabaseConnection) -> APIRouter:
    """creates and configures bookings api router with injected database dependencies"""
    controller = _assemble_controller(db)
    router = APIRouter(tags=["bookings"])

    @router.post(
        "",
        response_model=BookingResponse,
        status_code=201,
        summary="Create single meeting booking",
        responses={
            201: {"description": "Booking successfully created"},
            404: {"description": "Target room not found"},
            409: {"description": "Time slot conflict with existing active booking"},
            422: {"description": "Validation error or invalid local time in DST gap"},
        },
    )
    async def create_single_booking(
        request: BookingCreateRequest,
    ) -> BookingResponse:
        """creates a single meeting reservation ensuring room existence and zero conflicts"""
        return await controller.create_booking(request)

    @router.post(
        "/recurring",
        response_model=RecurringBookingResponse,
        status_code=201,
        summary="Create recurring meeting series",
        responses={
            201: {"description": "Recurring series created (skipping up to 2 clashes)"},
            404: {"description": "Target room not found"},
            409: {
                "description": "Series rejected: clashes exceed threshold (max 2 allowed, at least 50% must succeed)"
            },
            422: {"description": "Validation error or invalid recurrence parameters"},
        },
    )
    async def create_recurring_booking(
        request: RecurringBookingCreateRequest,
    ) -> RecurringBookingResponse:
        """creates a weekly recurring series upfront under the 50% + max 2 conflict policy"""
        return await controller.create_recurring(request)

    @router.delete(
        "/{booking_id}",
        response_model=CancelBookingResponse,
        summary="Cancel single standalone booking",
        responses={
            200: {"description": "Booking successfully cancelled and slot freed"},
            400: {
                "description": "Bad Request: Cannot cancel an individual occurrence of a recurring series (must cancel entire series via DELETE /api/v1/bookings/series/{series_id})"
            },
            404: {"description": "Booking not found"},
        },
    )
    async def cancel_single_booking(
        booking_id: int,
    ) -> CancelBookingResponse:
        """soft-deletes a single booking; returns 400 if booking belongs to a recurring series"""
        return await controller.cancel_booking(booking_id)

    @router.delete(
        "/series/{series_id}",
        response_model=CancelSeriesResponse,
        summary="Cancel all future occurrences of a recurring series",
        responses={
            200: {
                "description": "Future occurrences cancelled; past meetings preserved for reporting"
            },
            404: {"description": "Series or room not found"},
        },
    )
    async def cancel_series_bookings(
        series_id: int,
    ) -> CancelSeriesResponse:
        """cancels future series instances based on room-local cutoff resolving om-1"""
        return await controller.cancel_series(series_id)

    return router
