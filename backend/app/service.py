"""Glue: fetch SEPTA data -> labeled arrivals -> recommendation -> compact API response."""

from __future__ import annotations

import math
from collections.abc import Callable
from datetime import datetime

from app.api.schemas import ArrivalOut, CommuteOut, DataInfo, RecommendationOut, RouteOut
from app.config import CommuteMode, Settings
from app.predictions.arrivals import Arrival, build_arrivals, usable_snapshot
from app.recommendations.engine import Plan, Recommendation, RouteArrivals, recommend
from app.transit.client import Fetched, TransitClient
from app.transit.models import TripUpdatesSnapshot


def _epoch(dt: datetime | None) -> int | None:
    return math.floor(dt.timestamp()) if dt else None


def data_info(tu: Fetched, now: datetime, settings: Settings) -> DataInfo:
    snapshot = usable_snapshot(tu.value, now, settings)
    if snapshot is None:
        status, age = "offline", None
        if tu.value is not None:
            age = math.floor((now - tu.value.feed_timestamp).total_seconds())
    else:
        age = math.floor((now - snapshot.feed_timestamp).total_seconds())
        status = "stale" if age > settings.stale_after_s else "live"
    return DataInfo(status=status, feed_age_s=age, fetched_at=_epoch(tu.fetched_at), error=tu.error)


def _arrival_out(p: Plan, now: datetime) -> ArrivalOut:
    a = p.arrival
    return ArrivalOut(
        at=_epoch(a.at),
        in_s=math.floor((a.at - now).total_seconds()),
        kind=a.kind.value,
        catch=p.catch.value,
        leave_at=_epoch(p.leave_at),
        trip=a.trip_id,
        veh=a.vehicle_id,
        sched=_epoch(a.scheduled),
        dest=a.headsign,
    )


def _rec_out(r: Recommendation, settings: Settings) -> RecommendationOut:
    return RecommendationOut(
        route=r.route,
        action=r.action.value,
        leave_at=_epoch(r.plan.leave_at),
        leave_in_s=r.leave_in_s,
        arrives_at=_epoch(r.plan.arrival.at),
        kind=r.plan.arrival.kind.value,
        approx=r.approximate,
        reason=r.reason,
        ready_s=math.floor(settings.get_ready_window_min * 60),
    )


def build_response(
    mode: CommuteMode,
    settings: Settings,
    now: datetime,
    arrivals_by_route: dict[str, list[Arrival]],
    data: DataInfo,
    *,
    simulated: bool = False,
    scenario: str | None = None,
) -> CommuteOut:
    base = dict(
        mode=mode.key, label=mode.label, now=_epoch(now), data=data,
        simulated=simulated, scenario=scenario,
    )
    if not mode.configured:
        return CommuteOut(
            **base, configured=False, rec=None, routes=[],
            message=f"{mode.label} isn't set up yet. Add the boarding stop to the profile.",
        )

    route_inputs = [
        RouteArrivals(o.route, o.walk_min, arrivals_by_route.get(o.route, []))
        for o in mode.options
    ]
    rec, plans = recommend(route_inputs, mode.preferred_route, settings, now)
    n = settings.arrivals_per_route
    routes = [
        RouteOut(
            route=o.route,
            stop=o.stop_name,
            walk_min=o.walk_min,
            preferred=o.route == mode.preferred_route,
            arrivals=[_arrival_out(p, now) for p in plans.get(o.route, [])[:n]],
        )
        for o in mode.options
    ]

    message = None
    if rec is None:
        if not any(r.arrivals for r in routes):
            message = (
                "No live or scheduled buses available"
                if data.status != "offline"
                else "Live data unavailable and no scheduled buses found"
            )
        else:
            message = "No bus catchable with the current buffer"
    return CommuteOut(
        **base, configured=True, rec=_rec_out(rec, settings) if rec else None, routes=routes,
        message=message,
    )


async def commute_status(
    client: TransitClient, mode: CommuteMode, settings: Settings, clock: Callable[[], datetime]
) -> CommuteOut:
    if not mode.configured:
        now = clock()
        empty = Fetched(None, None, None)
        return build_response(mode, settings, now, {}, data_info(empty, now, settings))

    tu = await client.trip_updates()
    scheds = {o.route: await client.schedule(o.stop_id, o.route) for o in mode.options}
    now = clock()  # after fetching, so `now` is never earlier than the data
    snapshot: TripUpdatesSnapshot | None = tu.value
    arrivals: dict[str, list[Arrival]] = {}
    errors = [tu.error] if tu.error else []
    for opt in mode.options:
        sched = scheds[opt.route]
        if sched.error:
            errors.append(f"schedule {opt.route}: {sched.error}")
        arrivals[opt.route] = build_arrivals(opt, now, snapshot, sched.value, settings)

    info = data_info(tu, now, settings)
    if errors:
        info.error = "; ".join(errors)
    return build_response(mode, settings, now, arrivals, info)
