from datetime import date, datetime, timedelta
import re
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

ISO_NAIVE_REGEX = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}$")


class TimeValidationError(Exception):
    """raised when a datetime fails format, ordering, or timezone validity checks"""

    pass


def parse_naive_iso(iso_str: str) -> datetime:
    """parses strict naive iso string yyyy-mm-ddthh:mm:ss"""
    if not isinstance(iso_str, str) or not ISO_NAIVE_REGEX.match(iso_str):
        raise TimeValidationError(
            f"Invalid naive ISO timestamp '{iso_str}'. Expected format: YYYY-MM-DDTHH:MM:SS"
        )
    try:
        return datetime.fromisoformat(iso_str)
    except ValueError as err:
        raise TimeValidationError(
            f"Invalid timestamp value '{iso_str}': {err}"
        ) from err


def format_naive_iso(dt: datetime) -> str:
    """formats datetime into canonical naive iso string yyyy-mm-ddthh:mm:ss"""
    if not isinstance(dt, datetime):
        raise TypeError(f"Expected datetime instance, got {type(dt).__name__}")
    return dt.strftime("%Y-%m-%dT%H:%M:%S")


def get_zone_info(tz_name: str) -> ZoneInfo:
    """retrieves validated zoneinfo instance or raises timevalidationerror"""
    if not isinstance(tz_name, str) or not tz_name.strip():
        raise TimeValidationError(
            f"Timezone name must be a non-empty string, got '{tz_name}'"
        )
    try:
        return ZoneInfo(tz_name.strip())
    except ZoneInfoNotFoundError as err:
        raise TimeValidationError(f"Unknown timezone '{tz_name}'") from err


def validate_local_wall_time(dt: datetime, tz_name: str) -> None:
    """validates that a local wall-clock time exists and does not fall in a dst spring-forward gap"""
    tz = get_zone_info(tz_name)

    # fold 0 is the default resolution; in a spring-forward gap, converting to utc and back shifts the wall time
    localized_0 = dt.replace(tzinfo=tz, fold=0)
    utc_0 = localized_0.astimezone(ZoneInfo("UTC"))
    back_0 = utc_0.astimezone(tz).replace(tzinfo=None)

    if back_0 != dt:
        raise TimeValidationError(
            f"Local time '{dt.isoformat()}' does not exist in timezone '{tz_name}' due to DST spring-forward transition"
        )


def generate_weekly_occurrences(
    start_dt: datetime,
    end_dt: datetime,
    repeat_until: date,
    tz_name: str,
) -> list[tuple[datetime, datetime]]:
    """generates weekly wall-clock occurrences preserving local wall time across dst transitions"""
    if not isinstance(start_dt, datetime) or not isinstance(end_dt, datetime):
        raise TypeError("start_dt and end_dt must be datetime instances")
    if not isinstance(repeat_until, date):
        raise TypeError("repeat_until must be a date instance")

    if end_dt <= start_dt:
        raise TimeValidationError(
            "end datetime must be strictly after start datetime"
        )

    if repeat_until < start_dt.date():
        raise TimeValidationError(
            "repeat_until date cannot be earlier than start date"
        )

    duration: timedelta = end_dt - start_dt
    if duration >= timedelta(days=7):
        raise TimeValidationError("single meeting duration must be less than 7 days")

    occurrences: list[tuple[datetime, datetime]] = []
    current_start = start_dt

    while current_start.date() <= repeat_until:
        current_end = current_start + duration
        # validate that occurrence wall times exist in the room timezone
        validate_local_wall_time(current_start, tz_name)
        validate_local_wall_time(current_end, tz_name)
        occurrences.append((current_start, current_end))
        # weekly repetition by adding exactly 7 calendar days to naive datetime
        current_start += timedelta(days=7)

    return occurrences
