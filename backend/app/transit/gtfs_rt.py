"""Parse SEPTA's GTFS-Realtime Trip Updates feed."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, datetime

from google.protobuf.message import DecodeError
from google.transit import gtfs_realtime_pb2 as rt

from .models import StopPrediction, TransitDataError, TripState, TripUpdatesSnapshot

TRIP_UPDATES_URL = "https://www3.septa.org/gtfsrt/septa-pa-us/Trip/rtTripUpdates.pb"

_SKIPPED = rt.TripUpdate.StopTimeUpdate.SKIPPED
_CANCELED = rt.TripDescriptor.CANCELED


def _ts(seconds: int) -> datetime:
    return datetime.fromtimestamp(seconds, tz=UTC)


def parse_trip_updates(
    content: bytes,
    routes: Iterable[str],
    stop_ids: Iterable[str],
) -> TripUpdatesSnapshot:
    """Extract predictions for `stop_ids` and trip states for `routes`.

    Only the routes and stops Sparrow cares about are kept. The full feed covers
    ~3,600 trips across the whole system.
    """
    routes = set(routes)
    stop_ids = set(stop_ids)
    feed = rt.FeedMessage()
    try:
        feed.ParseFromString(content)
    except DecodeError as exc:
        raise TransitDataError(f"trip updates feed is not valid GTFS-RT: {exc}") from exc
    if not feed.header.timestamp:
        raise TransitDataError("trip updates feed has no header timestamp")

    snapshot = TripUpdatesSnapshot(feed_timestamp=_ts(feed.header.timestamp))

    for entity in feed.entity:
        if not entity.HasField("trip_update") or entity.is_deleted:
            continue
        tu = entity.trip_update
        trip = tu.trip
        if trip.route_id not in routes or not trip.trip_id:
            continue
        direction = trip.direction_id if trip.HasField("direction_id") else None
        vehicle = tu.vehicle.id or None
        canceled = trip.schedule_relationship == _CANCELED
        trip_ts = _ts(tu.timestamp) if tu.timestamp else None

        snapshot.trips[trip.trip_id] = TripState(
            trip_id=trip.trip_id,
            route=trip.route_id,
            direction_id=direction,
            vehicle_id=vehicle,
            canceled=canceled,
            remaining_stop_ids=frozenset(
                s.stop_id for s in tu.stop_time_update if s.schedule_relationship != _SKIPPED
            ),
            skipped_stop_ids=frozenset(
                s.stop_id for s in tu.stop_time_update if s.schedule_relationship == _SKIPPED
            ),
        )
        if canceled:
            continue

        for stu in tu.stop_time_update:
            if stu.stop_id not in stop_ids or stu.schedule_relationship == _SKIPPED:
                continue
            if stu.HasField("arrival") and stu.arrival.time:
                when = stu.arrival.time
            elif stu.HasField("departure") and stu.departure.time:
                when = stu.departure.time
            else:
                continue  # no usable time
            snapshot.predictions.setdefault(stu.stop_id, []).append(
                StopPrediction(
                    route=trip.route_id,
                    trip_id=trip.trip_id,
                    direction_id=direction,
                    stop_id=stu.stop_id,
                    stop_sequence=stu.stop_sequence if stu.HasField("stop_sequence") else None,
                    arrival=_ts(when),
                    vehicle_id=vehicle,
                    trip_timestamp=trip_ts,
                )
            )

    for preds in snapshot.predictions.values():
        preds.sort(key=lambda p: p.arrival)
    return snapshot
