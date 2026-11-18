from datetime import UTC, datetime, timedelta

from app.config import RouteOption, Settings
from app.predictions.arrivals import Kind, build_arrivals
from app.transit.gtfs_rt import parse_trip_updates
from app.transit.models import ScheduledArrival
from tests.feedbuilder import Stop, Trip, build_feed

NOW = datetime(2026, 11, 18, 22, 0, tzinfo=UTC)
OPT = RouteOption(route="40", direction_id=1, stop_id="S", stop_name="Test", walk_min=4)
SET = Settings()


def m(minutes: float) -> datetime:
    return NOW + timedelta(minutes=minutes)


def snap(trips, header=NOW - timedelta(seconds=20)):
    return parse_trip_updates(build_feed(header, trips), {"40", "42"}, {"S"})


def sched(trip_id, minutes, route="40", direction=1):
    return ScheduledArrival(route, trip_id, direction, "S", m(minutes))


def test_live_with_vehicle_is_live_and_without_is_estimated():
    s = snap([Trip("a", stops=[Stop("S", m(5))]), Trip("b", vehicle=None, stops=[Stop("S", m(9))])])
    out = build_arrivals(OPT, NOW, s, [], SET)
    assert [(a.trip_id, a.kind) for a in out] == [("a", Kind.LIVE), ("b", Kind.ESTIMATED)]


def test_wrong_direction_excluded():
    s = snap([Trip("a", direction_id=0, stops=[Stop("S", m(5))])])
    out = build_arrivals(OPT, NOW, s, [sched("x", 12, direction=0)], SET)
    assert out == []


def test_unknown_direction_kept_because_stop_is_direction_specific():
    s = snap([Trip("a", direction_id=None, stops=[Stop("S", m(5))])])
    assert len(build_arrivals(OPT, NOW, s, [], SET)) == 1


def test_wrong_route_excluded():
    s = snap([Trip("a", route="42", stops=[Stop("S", m(5))])])
    assert build_arrivals(OPT, NOW, s, [sched("x", 8, route="42")], SET) == []


def test_live_overrides_schedule_for_same_trip_and_keeps_scheduled_time():
    s = snap([Trip("a", stops=[Stop("S", m(3))])])  # early: scheduled at +6
    out = build_arrivals(OPT, NOW, s, [sched("a", 6)], SET)
    assert len(out) == 1
    assert out[0].at == m(3) and out[0].scheduled == m(6) and out[0].kind == Kind.LIVE


def test_scheduled_only_trips_fill_in_and_are_labeled():
    s = snap([Trip("a", stops=[Stop("S", m(4))])])
    out = build_arrivals(OPT, NOW, s, [sched("a", 4), sched("b", 14), sched("c", 24)], SET)
    assert [(a.trip_id, a.kind) for a in out] == [
        ("a", Kind.LIVE),
        ("b", Kind.SCHEDULED),
        ("c", Kind.SCHEDULED),
    ]


def test_scheduled_trip_that_already_passed_stop_is_dropped():
    # Trip b is in the live feed but no longer lists stop S -> bus already went by.
    s = snap([Trip("b", stops=[Stop("LATER", m(2))])])
    assert build_arrivals(OPT, NOW, s, [sched("b", 1)], SET) == []


def test_canceled_and_skipped_scheduled_trips_dropped():
    s = snap(
        [
            Trip("c", canceled=True, stops=[]),
            Trip("d", stops=[Stop("S", skipped=True), Stop("N", m(9))]),
        ]
    )
    assert build_arrivals(OPT, NOW, s, [sched("c", 5), sched("d", 8)], SET) == []


def test_prediction_in_the_past_beyond_grace_dropped():
    s = snap([Trip("a", stops=[Stop("S", m(-2))]), Trip("b", stops=[Stop("S", m(-0.5))])])
    assert [a.trip_id for a in build_arrivals(OPT, NOW, s, [], SET)] == ["b"]


def test_past_scheduled_time_dropped():
    assert build_arrivals(OPT, NOW, None, [sched("a", -1), sched("b", 1)], SET)[0].trip_id == "b"


def test_stale_feed_marks_live_as_stale():
    s = snap([Trip("a", stops=[Stop("S", m(5))])], header=NOW - timedelta(seconds=200))
    out = build_arrivals(OPT, NOW, s, [], SET)
    assert out[0].kind == Kind.STALE
    assert out[0].data_age_s == 200


def test_stale_single_trip_in_fresh_feed():
    s = snap(
        [
            Trip("a", stops=[Stop("S", m(5))], timestamp=NOW - timedelta(seconds=400)),
            Trip("b", stops=[Stop("S", m(8))]),
        ]
    )
    kinds = {a.trip_id: a.kind for a in build_arrivals(OPT, NOW, s, [], SET)}
    assert kinds == {"a": Kind.STALE, "b": Kind.LIVE}


def test_very_old_feed_discarded_and_schedule_used():
    s = snap([Trip("a", stops=[Stop("S", m(5))])], header=NOW - timedelta(seconds=900))
    out = build_arrivals(OPT, NOW, s, [sched("a", 6)], SET)
    assert [(a.trip_id, a.kind) for a in out] == [("a", Kind.SCHEDULED)]


def test_no_data_at_all_is_empty_not_invented():
    assert build_arrivals(OPT, NOW, None, None, SET) == []


def test_fewer_than_three_returned_as_is():
    s = snap([Trip("a", stops=[Stop("S", m(5))])])
    assert len(build_arrivals(OPT, NOW, s, [], SET)) == 1
