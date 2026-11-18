from datetime import UTC, datetime, timedelta

import pytest

from app.config import Settings
from app.predictions.arrivals import Arrival, Kind
from app.recommendations.engine import (
    Action,
    Catch,
    RouteArrivals,
    floor_minutes,
    plan_arrival,
    recommend,
)

NOW = datetime(2026, 11, 18, 22, 0, tzinfo=UTC)
SET = Settings()  # buffer 2, threshold 5, get-ready 3
WALK = {"40": 4.0, "42": 7.0}


def arr(route, minutes, kind=Kind.LIVE, trip=None):
    return Arrival(route, trip or f"{route}-{minutes}", "S", NOW + timedelta(minutes=minutes), kind)


def routes(r40=(), r42=()):
    return [
        RouteArrivals("40", WALK["40"], [arr("40", m) for m in r40]),
        RouteArrivals("42", WALK["42"], [arr("42", m) for m in r42]),
    ]


def rec(r40=(), r42=(), settings=SET, now=NOW):
    return recommend(routes(r40, r42), "40", settings, now)[0]


# --- the spec's example table ----------------------------------------------------------


@pytest.mark.parametrize(
    "r40, r42, expected",
    [
        ((8,), (10,), "40"),
        ((12,), (10,), "40"),
        ((27,), (11,), "42"),
        ((3,), (12,), "42"),  # first 40 can't be caught
        ((3, 18), (12,), "42"),  # next catchable 40 is 6 min after the 42
        ((3, 16), (12,), "40"),  # next catchable 40 within 5 min of the 42
    ],
)
def test_route_preference_table(r40, r42, expected):
    assert rec(r40, r42).route == expected


def test_spec_countdown_example():
    # 40 in 11 min, walk 4, buffer 2 -> leave in 5 min
    r = rec((11,))
    assert r.route == "40" and r.action == Action.LEAVE_IN
    assert r.leave_in_s == 300 and floor_minutes(r.leave_in_s) == 5


def test_threshold_is_configurable():
    strict = Settings(preference_threshold_min=1)
    assert rec((12,), (10,), settings=strict).route == "42"
    loose = Settings(preference_threshold_min=20)
    assert rec((27,), (11,), settings=loose).route == "40"


def test_threshold_boundary_is_inclusive():
    assert rec((15,), (10,)).route == "40"  # exactly 5 min later
    assert rec((15.1,), (10,)).route == "42"


# --- catchability ----------------------------------------------------------------------


def test_catch_states():
    a = arr("40", 6.5)  # slack +0.5
    assert plan_arrival(a, 4, 2, NOW).catch == Catch.OK
    b = arr("40", 5)  # slack -1: needs to eat buffer
    assert plan_arrival(b, 4, 2, NOW).catch == Catch.TIGHT
    c = arr("40", 3.9)  # can't even walk there
    assert plan_arrival(c, 4, 2, NOW).catch == Catch.MISSED


def test_tight_bus_not_recommended():
    r = rec((5, 20))
    assert r.plan.arrival.at == NOW + timedelta(minutes=20)


def test_early_bus_changes_recommendation():
    # The 40 was predicted at 12 min, then jumps 5 min earlier (early bus): now tight.
    before = rec((12, 25), (14,))
    after = rec((7, 25), (14,))
    assert before.route == "40" and before.leave_in_s == 360
    assert after.route == "40" and after.leave_in_s == 60  # 7-4-2 = 1 min


def test_missed_bus_falls_to_next():
    r = rec((1, 14), ())
    assert r.plan.arrival.at == NOW + timedelta(minutes=14)


def test_passing_time_moves_recommendation_forward():
    # Same predictions, later "now": the first bus becomes uncatchable.
    r1 = rec((10, 22), now=NOW)
    r2 = rec((10, 22), now=NOW + timedelta(minutes=4, seconds=30))
    assert r1.plan.arrival.at == NOW + timedelta(minutes=10)
    assert r2.plan.arrival.at == NOW + timedelta(minutes=22)


def test_buses_bunched_together():
    r = rec((9, 9.5, 10), ())
    assert r.plan.arrival.at == NOW + timedelta(minutes=9)


# --- actions and rounding --------------------------------------------------------------


@pytest.mark.parametrize(
    "minutes, action",
    [
        (6.5, Action.LEAVE_NOW),  # slack 30 s
        (7.5, Action.GET_READY),  # slack 90 s
        (8.9, Action.GET_READY),  # slack 174 s
        (9.0, Action.LEAVE_IN),  # slack 180 s
        (30, Action.LEAVE_IN),
    ],
)
def test_actions(minutes, action):
    assert rec((minutes,)).action == action


def test_countdown_floors_never_overstates():
    r = rec((11.99,))  # slack 5.99 min
    assert floor_minutes(r.leave_in_s) == 5
    assert r.leave_in_s == 359


# --- missing / degraded data -----------------------------------------------------------


def test_no_arrivals_no_recommendation():
    r, plans = recommend(routes(), "40", SET, NOW)
    assert r is None and plans == {"40": [], "42": []}


def test_nothing_catchable_no_recommendation():
    assert rec((2,), (5,)) is None


def test_only_alternative_route_available():
    r = rec((), (15,))
    assert r.route == "42" and "No upcoming 40" in r.reason


def test_scheduled_recommendation_is_marked_approximate():
    rs = [RouteArrivals("40", 4, [arr("40", 12, kind=Kind.SCHEDULED)])]
    r, _ = recommend(rs, "40", SET, NOW)
    assert r.approximate


def test_live_recommendation_not_approximate():
    assert not rec((12,)).approximate


def test_unsorted_input_is_sorted():
    rs = [RouteArrivals("40", 4, [arr("40", 20), arr("40", 10)])]
    r, plans = recommend(rs, "40", SET, NOW)
    assert r.plan.arrival.at == NOW + timedelta(minutes=10)
    assert [p.arrival.at for p in plans["40"]] == sorted(p.arrival.at for p in plans["40"])
