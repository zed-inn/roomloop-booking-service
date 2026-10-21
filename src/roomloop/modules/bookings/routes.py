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

    @router.post("", response_model=BookingResponse, status_code=201)
    async def create_single_booking(
        request: BookingCreateRequest,
    ) -> BookingResponse:
        return await controller.create_booking(request)

    @router.post("/recurring", response_model=RecurringBookingResponse, status_code=201)
    async def create_recurring_booking(
        request: RecurringBookingCreateRequest,
    ) -> RecurringBookingResponse:
        return await controller.create_recurring(request)

    @router.delete("/{booking_id}", response_model=CancelBookingResponse)
    async def cancel_single_booking(
        booking_id: int,
    ) -> CancelBookingResponse:
        return await controller.cancel_booking(booking_id)

    @router.delete("/series/{series_id}", response_model=CancelSeriesResponse)
    async def cancel_series_bookings(
        series_id: int,
    ) -> CancelSeriesResponse:
        return await controller.cancel_series(series_id)

    return router


def create_series_router(db: DatabaseConnection) -> APIRouter:
    """creates and configures series api router for root /series endpoints"""
    controller = _assemble_controller(db)
    router = APIRouter(tags=["series"])

    @router.delete("/{series_id}", response_model=CancelSeriesResponse)
    async def cancel_series(
        series_id: int,
    ) -> CancelSeriesResponse:
        return await controller.cancel_series(series_id)

    return router
