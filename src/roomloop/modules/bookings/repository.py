from sqlalchemy import select
from sqlalchemy.orm import Session

from roomloop.modules.bookings.model import BookingModel, SeriesModel


class BookingRepository:
    """database query and persistence operations for bookings and series entities"""

    def find_conflicts(
        self,
        session: Session,
        room_id: int,
        start_local: str,
        end_local: str,
    ) -> list[BookingModel]:
        """queries active bookings overlapping the half-open interval [start_local, end_local)"""
        stmt = (
            select(BookingModel)
            .where(
                BookingModel.room_id == room_id,
                BookingModel.status == "active",
                BookingModel.start_local < end_local,
                BookingModel.end_local > start_local,
            )
            .order_by(BookingModel.start_local.asc())
        )
        return list(session.scalars(stmt).all())

    def create_booking(self, session: Session, booking: BookingModel) -> BookingModel:
        """adds and flushes a booking record in the active session"""
        session.add(booking)
        session.flush()
        return booking

    def create_series(self, session: Session, series: SeriesModel) -> SeriesModel:
        """adds and flushes a series parent record in the active session"""
        session.add(series)
        session.flush()
        return series

    def get_booking_by_id(
        self, session: Session, booking_id: int
    ) -> BookingModel | None:
        """fetches booking by primary key id"""
        return session.get(BookingModel, booking_id)

    def get_series_by_id(self, session: Session, series_id: int) -> SeriesModel | None:
        """fetches series by primary key id"""
        return session.get(SeriesModel, series_id)

    def cancel_booking(
        self, session: Session, booking: BookingModel, now_utc: str
    ) -> BookingModel:
        """soft-deletes a single booking record by updating status to cancelled"""
        booking.status = "cancelled"
        booking.cancelled_at_utc = now_utc
        session.flush()
        return booking

    def cancel_future_series_bookings(
        self,
        session: Session,
        series_id: int,
        cutoff_local_str: str,
        now_utc: str,
    ) -> tuple[int, int]:
        """cancels future bookings of a series and preserves past or in-progress active ones"""
        stmt = select(BookingModel).where(BookingModel.series_id == series_id)
        series_bookings = list(session.scalars(stmt).all())

        cancelled_count = 0
        kept_count = 0

        for booking in series_bookings:
            if booking.start_local > cutoff_local_str and booking.status == "active":
                booking.status = "cancelled"
                booking.cancelled_at_utc = now_utc
                cancelled_count += 1
            elif booking.status == "active":
                kept_count += 1

        session.flush()
        return cancelled_count, kept_count
