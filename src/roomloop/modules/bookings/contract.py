from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class BookingCreateRequest(BaseModel):
    """request dto for creating a single meeting booking"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    room_id: int = Field(ge=1, description="Target room identifier")
    start: str = Field(
        pattern=r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}$",
        description="Naive ISO start timestamp YYYY-MM-DDTHH:MM:SS",
    )
    end: str = Field(
        pattern=r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}$",
        description="Naive ISO end timestamp YYYY-MM-DDTHH:MM:SS",
    )
    user: str = Field(
        min_length=1, max_length=100, description="Booker name or identifier"
    )


class RecurringBookingCreateRequest(BaseModel):
    """request dto for creating a recurring series of bookings"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    room_id: int = Field(ge=1, description="Target room identifier")
    start: str = Field(
        pattern=r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}$",
        description="First instance naive ISO start YYYY-MM-DDTHH:MM:SS",
    )
    end: str = Field(
        pattern=r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}$",
        description="First instance naive ISO end YYYY-MM-DDTHH:MM:SS",
    )
    user: str = Field(
        min_length=1, max_length=100, description="Booker name or identifier"
    )
    repeat_until: date = Field(
        description="Inclusive end date for weekly recurrence series"
    )


class BookingResponse(BaseModel):
    """response dto for a confirmed meeting booking instance matching contract c1"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: int
    room_id: int
    series_id: int | None
    user: str
    start: str
    end: str
    status: Literal["active", "cancelled"]
    created_at_utc: str


class SkippedInstance(BaseModel):
    """details of an instance skipped due to conflict per r2"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    start: str
    end: str
    reason: str


class RecurringBookingResponse(BaseModel):
    """response dto for a recurring booking series creation"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    series_id: int
    total_requested: int
    created_count: int
    skipped_count: int
    created: list[BookingResponse]
    skipped: list[SkippedInstance]
