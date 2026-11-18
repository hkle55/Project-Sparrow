"""Parse SEPTA's BusSchedules JSON API (today's scheduled times at a stop)."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from .models import ScheduledArrival, TransitDataError

log = logging.getLogger(__name__)

BUS_SCHEDULES_URL = "https://www3.septa.org/api/BusSchedules/index.php"


def schedule_params(stop_id: str, route: str, count: int) -> dict[str, str]:
    return {"stop_id": stop_id, "req2": route, "req6": str(count)}


def parse_local_datetime(text: str, tz: ZoneInfo) -> datetime:
    """Parse BusSchedules' 'MM/DD/YY hh:mm am' local time into UTC.

    During the DST fall-back hour, 1:xx am happens twice and the API doesn't say
    which one it means. We assume the first (fold=0, EDT), which is the earlier
    instant. That's the conservative choice for catching a bus.
    """
    naive = datetime.strptime(text.strip().upper(), "%m/%d/%y %I:%M %p")
    return naive.replace(tzinfo=tz).astimezone(UTC)


def parse_bus_schedules(
    payload: object, route: str, stop_id: str, tz: ZoneInfo
) -> list[ScheduledArrival]:
    if not isinstance(payload, dict):
        raise TransitDataError("BusSchedules response is not a JSON object")
    rows = payload.get(route, [])
    if not isinstance(rows, list):
        raise TransitDataError(f"BusSchedules route {route!r} is not a list")

    out: list[ScheduledArrival] = []
    for row in rows:
        try:
            direction = row.get("Direction")
            out.append(
                ScheduledArrival(
                    route=str(row["Route"]),
                    trip_id=str(row["trip_id"]),
                    direction_id=int(direction) if direction not in (None, "") else None,
                    stop_id=stop_id,
                    scheduled=parse_local_datetime(row["DateCalender"], tz),
                    headsign=row.get("DirectionDesc"),
                )
            )
        except (KeyError, ValueError, TypeError, AttributeError) as exc:
            log.warning("skipping malformed BusSchedules row %r: %s", row, exc)
    out.sort(key=lambda a: a.scheduled)
    return out
