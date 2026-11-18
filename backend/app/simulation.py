"""Named demo scenarios for the device simulator.

Scenarios feed synthetic arrivals through the *real* recommendation engine, so they
also exercise the engine's behavior. Responses are always marked `simulated: true`
and must never be shown as live transit information.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta

from app.api.schemas import CommuteOut, DataInfo
from app.config import CommuteMode, Settings
from app.predictions.arrivals import Arrival, Kind
from app.service import build_response

L, S, ST = Kind.LIVE, Kind.SCHEDULED, Kind.STALE


def _a(route: str, minutes: float, now: datetime, kind: Kind = L, n: int = 0) -> Arrival:
    at = now + timedelta(minutes=minutes)
    vehicle = None if kind == S else "sim"
    return Arrival(route, f"sim-{route}-{n}", "sim", at, kind, vehicle_id=vehicle)


def _routes(now: datetime, kind: Kind = L, **mins: tuple[float, ...]) -> dict[str, list[Arrival]]:
    return {
        r.removeprefix("r"): [_a(r.removeprefix("r"), m, now, kind, i) for i, m in enumerate(ms)]
        for r, ms in mins.items()
    }


Scenario = Callable[[datetime], tuple[dict[str, list[Arrival]], DataInfo]]

LIVE = DataInfo(status="live", feed_age_s=25, fetched_at=None)

SCENARIOS: dict[str, tuple[str, Scenario]] = {
    "normal": (
        "Normal commute",
        lambda now: (_routes(now, r40=(11, 25, 39), r42=(14, 28, 41)), LIVE),
    ),
    "early_bus": (
        "Bus running early: the 40 jumped from 12 to 7 min",
        lambda now: (_routes(now, r40=(7, 22, 36), r42=(16, 30, 44)), LIVE),
    ),
    "missed_preferred": (
        "Next 40 too close to catch",
        lambda now: (_routes(now, r40=(3, 24, 38), r42=(13, 27, 40)), LIVE),
    ),
    "route_42": (
        "Route 42 much sooner",
        lambda now: (_routes(now, r40=(27, 41, 55), r42=(13, 27, 41)), LIVE),
    ),
    "leave_now": ("Leave now", lambda now: (_routes(now, r40=(6.5, 20, 34), r42=(18, 32)), LIVE)),
    "stale": (
        "Live data is old",
        lambda now: (
            _routes(now, ST, r40=(12, 26), r42=(15, 29)),
            DataInfo(
                status="stale", feed_age_s=240, fetched_at=None, error="SEPTA feed not updating"
            ),
        ),
    ),
    "offline": (
        "SEPTA unreachable: schedule only",
        lambda now: (
            _routes(now, S, r40=(9, 19, 29), r42=(12, 22, 32)),
            DataInfo(status="offline", feed_age_s=None, fetched_at=None, error="ConnectTimeout"),
        ),
    ),
    "no_service": (
        "No buses running",
        lambda now: ({"40": [], "42": []}, LIVE),
    ),
}


def simulate(name: str, mode: CommuteMode, settings: Settings, now: datetime) -> CommuteOut:
    _, scenario = SCENARIOS[name]
    arrivals, info = scenario(now)
    return build_response(mode, settings, now, arrivals, info, simulated=True, scenario=name)
