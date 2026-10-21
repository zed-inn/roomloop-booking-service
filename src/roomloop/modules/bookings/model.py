from sqlalchemy import CheckConstraint, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from roomloop.shared.models.base import Base


class SeriesModel(Base):
    """persistent recurring series parent entity"""

    __tablename__ = "series"

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True
    )
    room_id: Mapped[int] = mapped_column(
        ForeignKey("rooms.id"), nullable=False, index=True
    )
    user_name: Mapped[str] = mapped_column(String(100), nullable=False)
    repeat_until: Mapped[str] = mapped_column(
        String(10), nullable=False
    )  # yyyy-mm-dd
    created_at_utc: Mapped[str] = mapped_column(String(30), nullable=False)
    cancelled_at_utc: Mapped[str | None] = mapped_column(
        String(30), nullable=True
    )

    bookings: Mapped[list["BookingModel"]] = relationship(
        back_populates="series"
    )


class BookingModel(Base):
    """persistent meeting room booking entity"""

    __tablename__ = "bookings"

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True
    )
    room_id: Mapped[int] = mapped_column(
        ForeignKey("rooms.id"), nullable=False, index=True
    )
    series_id: Mapped[int | None] = mapped_column(
        ForeignKey("series.id"), nullable=True, index=True
    )
    user_name: Mapped[str] = mapped_column(String(100), nullable=False)
    start_local: Mapped[str] = mapped_column(
        String(19), nullable=False
    )  # yyyy-mm-ddthh:mm:ss
    end_local: Mapped[str] = mapped_column(
        String(19), nullable=False
    )  # yyyy-mm-ddthh:mm:ss
    status: Mapped[str] = mapped_column(
        String(20), default="active", nullable=False
    )
    created_at_utc: Mapped[str] = mapped_column(String(30), nullable=False)
    cancelled_at_utc: Mapped[str | None] = mapped_column(
        String(30), nullable=True
    )

    series: Mapped[SeriesModel | None] = relationship(back_populates="bookings")

    __table_args__ = (
        CheckConstraint("start_local < end_local", name="chk_booking_times"),
        CheckConstraint(
            "status IN ('active', 'cancelled')", name="chk_booking_status"
        ),
        Index(
            "ix_bookings_active_search",
            "room_id",
            "status",
            "start_local",
            "end_local",
        ),
    )
