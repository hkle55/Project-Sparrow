"""Turn raw SEPTA data into a clean, labeled list of upcoming arrivals at one stop.

Rules (see docs/architecture.md for the reasoning):
- GTFS-RT trip updates win over the schedule for the same trip_id.
- A trip-update with a vehicle assigned is LIVE; without a vehicle, ESTIMATED.
- Live data older than `stale_after_s` is STALE; older than `discard_after_s` is ignored.
- A scheduled trip is dropped if the live feed shows it canceled, skipping this stop,
  or no longer listing this stop (meaning the bus already passed it).
- Wrong-route and wrong-direction entries are excluded.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum

from app.config import RouteOption, Settings
from app.transit.models import ScheduledArrival, TripUpdatesSnapshot

# A prediction slightly in the past may still be a bus sitting at the stop, but it can't
# be caught by someone who hasn't left yet. Beyond this grace it's treated as gone.
PASSED_GRACE = timedelta(seconds=60)


class Kind(StrEnum):
    LIVE = "live"  # agency prediction for a trip with a vehicle on it
    ESTIMATED = "estimated"  # agency prediction, but no vehicle assigned yet
    SCHEDULED = "scheduled"  # timetable only
    STALE = "stale"  # was live, but the data is too old to trust as live


@dataclass(frozen=True)
class Arrival:
    route: str
    trip_id: str
    stop_id: str
    at: datetime
    kind: Kind
    vehicle_id: str | None = None
    scheduled: datetime | None = None
    headsign: str | None = None
    data_age_s: float | None = None  # seconds since the agency generated this prediction


def snapshot_age_s(snapshot: TripUpdatesSnapshot, now: datetime) -> float:
    return (now - snapshot.feed_timestamp).total_seconds()


def usable_snapshot(
    snapshot: TripUpdatesSnapshot | None, now: datetime, settings: Settings
) -> TripUpdatesSnapshot | None:
    if snapshot is None or snapshot_age_s(snapshot, now) > settings.discard_after_s:
        return None
    return snapshot


def _direction_ok(actual: int | None, wanted: int) -> bool:
    # Stop IDs are already direction-specific; only reject a *known* mismatch.
    return actual is None or actual == wanted


def build_arrivals(
    option: RouteOption,
    now: datetime,
    snapshot: TripUpdatesSnapshot | None,
    scheduled: list[ScheduledArrival] | None,
    settings: Settings,
) -> list[Arrival]:
    snapshot = usable_snapshot(snapshot, now, settings)
    out: list[Arrival] = []
    live_trip_ids: set[str] = set()
    sched_by_trip = {s.trip_id: s for s in scheduled or []}

    if snapshot is not None:
        feed_age = snapshot_age_s(snapshot, now)
        for p in snapshot.for_stop(option.stop_id):
            if p.route != option.route or not _direction_ok(p.direction_id, option.direction_id):
                continue
            live_trip_ids.add(p.trip_id)
            if p.arrival < now - PASSED_GRACE:
                continue
            trip_age = (now - p.trip_timestamp).total_seconds() if p.trip_timestamp else feed_age
            age = max(feed_age, trip_age)
            if age > settings.discard_after_s:
                continue
            if age > settings.stale_after_s:
                kind = Kind.STALE
            elif p.vehicle_id:
                kind = Kind.LIVE
            else:
                kind = Kind.ESTIMATED
            sched = sched_by_trip.get(p.trip_id)
            out.append(
                Arrival(
                    route=p.route,
                    trip_id=p.trip_id,
                    stop_id=p.stop_id,
                    at=p.arrival,
                    kind=kind,
                    vehicle_id=p.vehicle_id,
                    scheduled=sched.scheduled if sched else None,
                    headsign=sched.headsign if sched else p.headsign,
                    data_age_s=age,
                )
            )

    for s in scheduled or []:
        if s.trip_id in live_trip_ids:
            continue
        if s.route != option.route or not _direction_ok(s.direction_id, option.direction_id):
            continue
        if s.scheduled < now:
            continue
        if snapshot is not None:
            trip = snapshot.trips.get(s.trip_id)
            if trip is not None and (
                trip.canceled
                or option.stop_id in trip.skipped_stop_ids
                or option.stop_id not in trip.remaining_stop_ids
            ):
                continue  # canceled, detoured around this stop, or already passed it
        out.append(
            Arrival(
                route=s.route,
                trip_id=s.trip_id,
                stop_id=s.stop_id,
                at=s.scheduled,
                kind=Kind.SCHEDULED,
                scheduled=s.scheduled,
                headsign=s.headsign,
            )
        )

    out.sort(key=lambda a: a.at)
    return out
