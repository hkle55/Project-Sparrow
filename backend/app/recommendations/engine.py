"""Departure recommendation engine. Pure functions only: no I/O, and `now` is always passed in.

    leave_at = predicted arrival - walking time - safety buffer
    slack    = leave_at - now

    slack >= 0                -> catchable with the full buffer ("ok")
    -buffer <= slack < 0      -> only by eating into the buffer ("tight"; shown, not recommended)
    slack < -buffer           -> can't walk there in time ("missed")

Route choice: take the next *ok* bus on each route. The preferred route wins unless another
route boards more than `preference_threshold_min` sooner.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum

from app.config import Settings
from app.predictions.arrivals import Arrival, Kind

LEAVE_NOW_WINDOW_S = 60  # under a minute of slack: just go


class Catch(StrEnum):
    OK = "ok"
    TIGHT = "tight"
    MISSED = "missed"


class Action(StrEnum):
    LEAVE_IN = "leave_in"
    GET_READY = "get_ready"
    LEAVE_NOW = "leave_now"
    NONE = "none"  # nothing catchable / no data


@dataclass(frozen=True)
class Plan:
    arrival: Arrival
    walk_min: float
    leave_at: datetime
    slack_s: float
    catch: Catch


@dataclass(frozen=True)
class RouteArrivals:
    route: str
    walk_min: float
    arrivals: list[Arrival]


@dataclass(frozen=True)
class Recommendation:
    route: str
    plan: Plan
    action: Action
    leave_in_s: int  # floored, never negative
    reason: str

    @property
    def approximate(self) -> bool:
        return self.plan.arrival.kind != Kind.LIVE


def plan_arrival(arrival: Arrival, walk_min: float, buffer_min: float, now: datetime) -> Plan:
    leave_at = arrival.at - timedelta(minutes=walk_min + buffer_min)
    slack = (leave_at - now).total_seconds()
    if slack >= 0:
        catch = Catch.OK
    elif slack >= -buffer_min * 60:
        catch = Catch.TIGHT
    else:
        catch = Catch.MISSED
    return Plan(arrival, walk_min, leave_at, slack, catch)


def action_for(slack_s: float, settings: Settings) -> Action:
    if slack_s < LEAVE_NOW_WINDOW_S:
        return Action.LEAVE_NOW
    if slack_s < settings.get_ready_window_min * 60:
        return Action.GET_READY
    return Action.LEAVE_IN


def floor_minutes(seconds: float) -> int:
    """Whole minutes, rounded *down*, so a countdown never promises more time than exists."""
    return max(0, math.floor(seconds / 60))


def next_catchable(plans: list[Plan]) -> Plan | None:
    return next((p for p in plans if p.catch == Catch.OK), None)


def recommend(
    routes: list[RouteArrivals],
    preferred_route: str | None,
    settings: Settings,
    now: datetime,
) -> tuple[Recommendation | None, dict[str, list[Plan]]]:
    """Return the recommendation (or None) and the per-route plans for display."""
    plans = {
        r.route: [
            plan_arrival(a, r.walk_min, settings.safety_buffer_min, now)
            for a in sorted(r.arrivals, key=lambda a: a.at)
        ]
        for r in routes
    }
    candidates = {route: p for route, ps in plans.items() if (p := next_catchable(ps))}
    if not candidates:
        return None, plans

    best_other = min(
        (p for route, p in candidates.items() if route != preferred_route),
        key=lambda p: p.arrival.at,
        default=None,
    )
    pref = candidates.get(preferred_route) if preferred_route else None
    threshold = timedelta(minutes=settings.preference_threshold_min)

    if pref is not None and best_other is None:
        chosen, reason = pref, f"Route {preferred_route} preferred"
    elif pref is None:
        chosen = best_other
        first_pref = plans.get(preferred_route, [])
        if preferred_route and first_pref:
            reason = f"Next {preferred_route} can't be caught"
        elif preferred_route:
            reason = f"No upcoming {preferred_route}"
        else:
            reason = "Earliest catchable bus"
    elif pref.arrival.at - best_other.arrival.at <= threshold:
        chosen, reason = pref, f"Route {preferred_route} preferred"
    else:
        chosen = best_other
        gain = floor_minutes((pref.arrival.at - best_other.arrival.at).total_seconds())
        reason = f"Boards {gain} min before next {preferred_route}"

    return (
        Recommendation(
            route=chosen.arrival.route,
            plan=chosen,
            action=action_for(chosen.slack_s, settings),
            leave_in_s=max(0, math.floor(chosen.slack_s)),
            reason=reason,
        ),
        plans,
    )
