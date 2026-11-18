"""Departure recommendation engine. Pure functions only: no I/O, and `now` is always passed in.

    leave_at = predicted arrival - walking time - safety buffer
    slack    = leave_at - now

    slack >= 0                -> catchable with the full buffer ("ok")
    -buffer <= slack < 0      -> reachable on foot, but only by cutting into the buffer ("tight")
    slack < -buffer           -> can't walk there in time ("missed")

Route choice: take the next *ok* bus on each route. The preferred route wins unless another
route boards more than `preference_threshold_min` sooner.

Tight connections: a tight bus is recommended (action TIGHT) only when no safe bus boards
within `tight_max_wait_min` after it. Otherwise the safer bus wins. When a tight bus is
recommended, the safe option is attached as the alternative.
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
    TIGHT = "tight"  # go immediately; you'll reach the stop with less than the full buffer
    NONE = "none"  # nothing catchable / no data


@dataclass(frozen=True)
class Plan:
    arrival: Arrival
    walk_min: float
    leave_at: datetime
    slack_s: float
    catch: Catch

    @property
    def margin_s(self) -> float:
        """Seconds you'd wait at the stop if you left right now and walked."""
        return self.slack_s + (self.arrival.at - self.leave_at).total_seconds() - self.walk_min * 60


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
    alternative: Recommendation | None = None  # safer option when action is TIGHT

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


def _safe_choice(
    plans: dict[str, list[Plan]], preferred_route: str | None, settings: Settings
) -> tuple[Plan, str] | None:
    candidates = {route: p for route, ps in plans.items() if (p := next_catchable(ps))}
    if not candidates:
        return None

    best_other = min(
        (p for route, p in candidates.items() if route != preferred_route),
        key=lambda p: p.arrival.at,
        default=None,
    )
    pref = candidates.get(preferred_route) if preferred_route else None
    threshold = timedelta(minutes=settings.preference_threshold_min)

    if pref is not None and best_other is None:
        return pref, f"Route {preferred_route} preferred"
    if pref is None:
        if preferred_route and plans.get(preferred_route):
            return best_other, f"Next {preferred_route} can't be caught"
        if preferred_route:
            return best_other, f"No upcoming {preferred_route}"
        return best_other, "Earliest catchable bus"
    if pref.arrival.at - best_other.arrival.at <= threshold:
        return pref, f"Route {preferred_route} preferred"
    gain = floor_minutes((pref.arrival.at - best_other.arrival.at).total_seconds())
    return best_other, f"Boards {gain} min before next {preferred_route}"


def _tight_choice(plans: dict[str, list[Plan]]) -> Plan | None:
    """The tight bus with the most margin, if any."""
    tight = [p for ps in plans.values() for p in ps if p.catch == Catch.TIGHT]
    return max(tight, key=lambda p: p.slack_s, default=None)


def _margin_text(plan: Plan) -> str:
    margin = plan.margin_s
    if margin < 60:
        return "under 1 min to spare"
    return f"about {floor_minutes(margin)} min to spare"


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

    safe = _safe_choice(plans, preferred_route, settings)
    safe_rec = None
    if safe is not None:
        chosen, reason = safe
        safe_rec = Recommendation(
            route=chosen.arrival.route,
            plan=chosen,
            action=action_for(chosen.slack_s, settings),
            leave_in_s=max(0, math.floor(chosen.slack_s)),
            reason=reason,
        )

    tight = _tight_choice(plans)
    max_wait = timedelta(minutes=settings.tight_max_wait_min)
    if tight is not None and (
        safe_rec is None or safe_rec.plan.arrival.at - tight.arrival.at > max_wait
    ):
        if safe_rec is None:
            reason = f"Tight: {_margin_text(tight)}, no safer bus"
        else:
            wait = floor_minutes((safe_rec.plan.arrival.at - tight.arrival.at).total_seconds())
            reason = f"Tight: {_margin_text(tight)}; safer bus is {wait} min later"
        return (
            Recommendation(
                route=tight.arrival.route,
                plan=tight,
                action=Action.TIGHT,
                leave_in_s=0,
                reason=reason,
                alternative=safe_rec,
            ),
            plans,
        )
    return safe_rec, plans
