from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class BookingCreateRequest(BaseModel):
    """request model for creating a single meeting reservation"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    room_id: int = Field(ge=1, description="Unique room identifier")
    start: str = Field(
        pattern=r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}$",
        description="Meeting start timestamp in naive local ISO format (YYYY-MM-DDTHH:MM:SS)",
        examples=["2026-11-10T09:00:00"],
    )
    end: str = Field(
        pattern=r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}$",
        description="Meeting end timestamp in naive local ISO format (YYYY-MM-DDTHH:MM:SS)",
        examples=["2026-11-10T10:00:00"],
    )
    user: str = Field(
        min_length=1,
        max_length=100,
        description="Organizer or attendee identifier",
        examples=["alex"],
    )


class RecurringBookingCreateRequest(BaseModel):
    """request model for creating a recurring weekly booking series"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    room_id: int = Field(ge=1, description="Unique room identifier")
    start: str = Field(
        pattern=r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}$",
        description="First instance start timestamp in naive local ISO format (YYYY-MM-DDTHH:MM:SS)",
        examples=["2026-11-04T14:00:00"],
    )
    end: str = Field(
        pattern=r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}$",
        description="First instance end timestamp in naive local ISO format (YYYY-MM-DDTHH:MM:SS)",
        examples=["2026-11-04T15:00:00"],
    )
    user: str = Field(
        min_length=1,
        max_length=100,
        description="Organizer or attendee identifier",
        examples=["engineering-team"],
    )
    repeat_until: date = Field(
        description="Inclusive end date for weekly recurrence series (YYYY-MM-DD)",
        examples=["2026-11-25"],
    )


class BookingResponse(BaseModel):
    """response model for confirmed meeting reservations conforming to reporting contract c1"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: int = Field(description="Unique booking identifier")
    room_id: int = Field(description="Associated room identifier")
    series_id: int | None = Field(
        default=None, description="Parent recurring series identifier, if applicable"
    )
    user: str = Field(description="Organizer or attendee identifier")
    start: str = Field(
        description="Meeting start timestamp in room-local naive ISO format"
    )
    end: str = Field(description="Meeting end timestamp in room-local naive ISO format")
    status: Literal["active", "cancelled"] = Field(
        description="Booking lifecycle status"
    )
    created_at_utc: str = Field(description="UTC timestamp of reservation creation")


class SkippedInstance(BaseModel):
    """details of a recurring instance skipped due to time slot conflicts"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    start: str = Field(description="Skipped instance start timestamp")
    end: str = Field(description="Skipped instance end timestamp")
    reason: str = Field(description="Explanation of schedule conflict")


class RecurringBookingResponse(BaseModel):
    """response model confirming recurring booking series creation"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    series_id: int = Field(description="Unique series identifier")
    total_requested: int = Field(
        description="Total candidate weekly occurrences evaluated"
    )
    created_count: int = Field(
        description="Number of meeting instances successfully booked"
    )
    skipped_count: int = Field(description="Number of conflicting instances skipped")
    created: list[BookingResponse] = Field(
        description="List of confirmed active bookings"
    )
    skipped: list[SkippedInstance] = Field(
        description="List of skipped conflicting occurrences"
    )


class CancelBookingResponse(BaseModel):
    """confirmation response for soft-deleted single booking"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: int = Field(description="Cancelled booking identifier")
    status: Literal["cancelled"] = Field(description="Updated booking status")
    cancelled_at_utc: str = Field(description="UTC timestamp of cancellation")


class CancelSeriesResponse(BaseModel):
    """confirmation response for cancelled future recurring series instances"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    series_id: int = Field(description="Identifier of dissolved series")
    cancelled_count: int = Field(description="Number of future instances soft-deleted")
    kept_count: int = Field(description="Number of past or ongoing instances preserved")
    cancelled_at_utc: str = Field(description="UTC timestamp of series dissolution")
