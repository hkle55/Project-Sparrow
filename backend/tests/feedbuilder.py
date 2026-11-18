"""Build small synthetic GTFS-RT trip-update feeds for deterministic tests."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from google.transit import gtfs_realtime_pb2 as rt


@dataclass
class Stop:
    stop_id: str
    at: datetime | None = None
    skipped: bool = False
    seq: int | None = None


@dataclass
class Trip:
    trip_id: str
    route: str = "40"
    direction_id: int | None = 1
    vehicle: str | None = "v1"
    stops: list[Stop] = field(default_factory=list)
    canceled: bool = False
    timestamp: datetime | None = None


def build_feed(header_ts: datetime, trips: list[Trip]) -> bytes:
    feed = rt.FeedMessage()
    feed.header.gtfs_realtime_version = "2.0"
    feed.header.timestamp = int(header_ts.timestamp())
    for i, t in enumerate(trips):
        e = feed.entity.add()
        e.id = f"e{i}"
        tu = e.trip_update
        tu.trip.trip_id = t.trip_id
        tu.trip.route_id = t.route
        if t.direction_id is not None:
            tu.trip.direction_id = t.direction_id
        if t.canceled:
            tu.trip.schedule_relationship = rt.TripDescriptor.CANCELED
        if t.vehicle:
            tu.vehicle.id = t.vehicle
        tu.timestamp = int((t.timestamp or header_ts).timestamp())
        for j, s in enumerate(t.stops):
            stu = tu.stop_time_update.add()
            stu.stop_id = s.stop_id
            stu.stop_sequence = s.seq if s.seq is not None else j + 1
            if s.skipped:
                stu.schedule_relationship = rt.TripUpdate.StopTimeUpdate.SKIPPED
            if s.at is not None:
                stu.arrival.time = int(s.at.timestamp())
    return feed.SerializeToString()
