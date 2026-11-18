"""Normalized transit data. All datetimes are timezone-aware UTC."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


class TransitDataError(Exception):
    """Upstream data was missing, malformed, or unreachable."""


@dataclass(frozen=True)
class StopPrediction:
    """A GTFS-RT predicted arrival of one trip at one stop."""

    route: str
    trip_id: str
    direction_id: int | None
    stop_id: str
    stop_sequence: int | None
    arrival: datetime
    vehicle_id: str | None
    trip_timestamp: datetime | None  # when the agency last updated this trip's prediction
    headsign: str | None = None
    start_date: str | None = None  # GTFS service date YYYYMMDD; trip_ids repeat every day


@dataclass(frozen=True)
class TripState:
    """What the trip-updates feed says about a trip overall (for passed/canceled checks)."""

    trip_id: str
    route: str
    direction_id: int | None
    vehicle_id: str | None
    canceled: bool
    remaining_stop_ids: frozenset[str]  # upcoming stops the bus will still serve
    skipped_stop_ids: frozenset[str] = frozenset()  # e.g. detours
    start_date: str | None = None


@dataclass
class TripUpdatesSnapshot:
    feed_timestamp: datetime
    predictions: dict[str, list[StopPrediction]] = field(default_factory=dict)  # by stop_id
    trips: dict[str, TripState] = field(default_factory=dict)  # by trip_id

    def for_stop(self, stop_id: str) -> list[StopPrediction]:
        return self.predictions.get(stop_id, [])


@dataclass(frozen=True)
class ScheduledArrival:
    route: str
    trip_id: str
    direction_id: int | None
    stop_id: str
    scheduled: datetime
    headsign: str | None = None


@dataclass(frozen=True)
class VehicleSample:
    """One GTFS-RT vehicle position: where a bus said it was, and when (GPS time)."""

    vehicle_id: str
    trip_id: str
    route: str
    direction_id: int | None
    start_date: str | None
    stop_sequence: int | None  # current_stop_sequence
    stop_id: str | None
    status: str  # INCOMING_AT / STOPPED_AT / IN_TRANSIT_TO
    timestamp: datetime  # vehicle's own report time
    lat: float | None
    lon: float | None


@dataclass
class VehicleSnapshot:
    feed_timestamp: datetime
    vehicles: list[VehicleSample] = field(default_factory=list)
