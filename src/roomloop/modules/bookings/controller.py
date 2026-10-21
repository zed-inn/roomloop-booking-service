from roomloop.modules.bookings.contract import (
    BookingCreateRequest,
    BookingResponse,
    RecurringBookingCreateRequest,
    RecurringBookingResponse,
)
from roomloop.modules.bookings.service import BookingService


class BookingController:
    """handles http endpoint dispatching for booking resources"""

    def __init__(self, booking_service: BookingService) -> None:
        self.booking_service = booking_service

    async def create_booking(
        self, request: BookingCreateRequest
    ) -> BookingResponse:
        """endpoint handler for creating a single meeting booking"""
        return self.booking_service.create_single_booking(request)

    async def create_recurring(
        self, request: RecurringBookingCreateRequest
    ) -> RecurringBookingResponse:
        """endpoint handler for creating a recurring series of bookings"""
        return self.booking_service.create_recurring_booking(request)
