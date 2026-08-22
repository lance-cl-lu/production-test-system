from datetime import datetime, timezone
from zoneinfo import ZoneInfo


TAIPEI_TZ = ZoneInfo("Asia/Taipei")


def utc_now() -> datetime:
    """Return UTC without tzinfo for MySQL DATETIME columns."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def to_utc_naive(value: datetime) -> datetime:
    """Normalize an API datetime to the UTC-naive database convention."""
    if value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def utc_iso(value: datetime | None) -> str | None:
    """Expose database UTC timestamps with an explicit UTC designator."""
    if value is None:
        return None
    return f"{to_utc_naive(value).isoformat()}Z"


def taipei_today_start_utc() -> datetime:
    """Return today's Taipei midnight converted to UTC-naive."""
    taipei_now = datetime.now(TAIPEI_TZ)
    taipei_midnight = taipei_now.replace(hour=0, minute=0, second=0, microsecond=0)
    return taipei_midnight.astimezone(timezone.utc).replace(tzinfo=None)
