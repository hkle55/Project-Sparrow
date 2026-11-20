"""Compact API response shapes, small enough for an ESP32 to parse.

All times are integer epoch seconds (UTC). Durations are integer seconds, floored.
The client should count down locally using `now` to correct for clock skew.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

DataStatus = Literal["live", "stale", "offline"]


class DataInfo(BaseModel):
    status: DataStatus  # live: fresh feed; stale: old feed; offline: no usable live feed
    feed_age_s: int | None  # seconds since SEPTA generated the data we're using
    fetched_at: int | None  # last successful fetch from SEPTA
    error: str | None = None  # most recent upstream problem, if any


class ArrivalOut(BaseModel):
    at: int
    in_s: int  # may be slightly negative for a bus at the stop right now
    kind: Literal["live", "estimated", "scheduled", "stale"]
    catch: Literal["ok", "tight", "missed"]
    leave_at: int
    trip: str
    veh: str | None = None
    sched: int | None = None  # scheduled time, when known
    dest: str | None = None


class RouteOut(BaseModel):
    route: str
    stop: str
    walk_min: float
    preferred: bool
    arrivals: list[ArrivalOut]


class AlternativeOut(BaseModel):
    """The safer bus, shown alongside a TIGHT recommendation."""

    route: str
    action: Literal["leave_in", "get_ready", "leave_now"]
    leave_at: int
    leave_in_s: int
    arrives_at: int
    kind: Literal["live", "estimated", "scheduled", "stale"]


class RecommendationOut(BaseModel):
    route: str
    action: Literal["leave_in", "get_ready", "leave_now", "tight"]
    leave_at: int
    leave_in_s: int
    arrives_at: int
    kind: Literal["live", "estimated", "scheduled", "stale"]
    approx: bool  # true unless based on a fresh live prediction
    reason: str
    ready_s: int  # client shows GET READY when leave_in_s drops below this (LEAVE NOW < 60)
    alt: AlternativeOut | None = None  # safer bus when action == "tight"


class CommuteOut(BaseModel):
    v: int = 1
    mode: str
    label: str
    auto: bool | None = None  # true when the server picked `mode` by time of day
    configured: bool
    simulated: bool = False
    scenario: str | None = None
    now: int
    data: DataInfo
    rec: RecommendationOut | None
    routes: list[RouteOut]
    message: str | None = None  # human-readable status line when there's no recommendation
