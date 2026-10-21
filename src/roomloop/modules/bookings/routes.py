from fastapi import APIRouter

from roomloop.config.database import DatabaseConnection
from roomloop.modules.audit.repository import AuditLogRepository
from roomloop.modules.bookings.contract import (
    BookingCreateRequest,
    BookingResponse,
    RecurringBookingCreateRequest,
    RecurringBookingResponse,
)
from roomloop.modules.bookings.controller import BookingController
from roomloop.modules.bookings.repository import BookingRepository
from roomloop.modules.bookings.service import BookingService
from roomloop.modules.rooms.repository import RoomRepository


def create_bookings_router(db: DatabaseConnection) -> APIRouter:
    """creates and configures bookings api router with injected database dependencies"""
    booking_repo = BookingRepository()
    room_repo = RoomRepository(db)
    audit_repo = AuditLogRepository(db)
    booking_service = BookingService(
        db=db,
        booking_repo=booking_repo,
        room_repo=room_repo,
        audit_repo=audit_repo,
    )
    controller = BookingController(booking_service)

    router = APIRouter(tags=["bookings"])

    @router.post("", response_model=BookingResponse, status_code=201)
    async def create_single_booking(
        request: BookingCreateRequest,
    ) -> BookingResponse:
        return await controller.create_booking(request)

    @router.post(
        "/recurring", response_model=RecurringBookingResponse, status_code=201
    )
    async def create_recurring_booking(
        request: RecurringBookingCreateRequest,
    ) -> RecurringBookingResponse:
        return await controller.create_recurring(request)

    return router
