import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from app.transit.gtfs_rt import parse_trip_updates
from app.transit.models import TransitDataError
from app.transit.schedules import parse_bus_schedules, parse_local_datetime
from tests.feedbuilder import Stop, Trip, build_feed

FIX = Path(__file__).parent / "fixtures"
NY = ZoneInfo("America/New_York")
T0 = datetime(2026, 11, 18, 22, 0, tzinfo=UTC)


# --- real captured feed (routes 40/42 only, captured 2026-11-18 ~17:23 ET) ---------------


@pytest.fixture(scope="module")
def real_snapshot():
    content = (FIX / "trip_updates_40_42.pb").read_bytes()
    return parse_trip_updates(content, {"40", "42"}, {"22265", "14884"})


def test_real_feed_header_timestamp(real_snapshot):
    assert real_snapshot.feed_timestamp == datetime.fromtimestamp(1795040602, UTC)


def test_real_feed_route40_westbound_stop(real_snapshot):
    preds = real_snapshot.for_stop("22265")
    assert len(preds) == 5
    assert {p.route for p in preds} == {"40"}
    assert {p.direction_id for p in preds} == {1}
    assert all(p.vehicle_id for p in preds)


def test_real_feed_sorted_by_predicted_time_not_trip_order(real_snapshot):
    preds = real_snapshot.for_stop("22265")
    times = [p.arrival for p in preds]
    assert times == sorted(times)
    # 964081 overtook 964083 (bunching) in the captured data
    assert [p.trip_id for p in preds[:2]] == ["964081", "964083"]


def test_real_feed_route42_stop(real_snapshot):
    preds = real_snapshot.for_stop("14884")
    assert len(preds) == 7
    assert {p.route for p in preds} == {"42"}


def test_real_feed_tracks_trip_states_for_both_directions(real_snapshot):
    dirs = {t.direction_id for t in real_snapshot.trips.values()}
    assert dirs == {0, 1}


# --- synthetic edge cases -----------------------------------------------------------------


def test_filters_other_routes_at_shared_stop():
    feed = build_feed(
        T0,
        [
            Trip("a", route="42", stops=[Stop("S", T0 + timedelta(minutes=5))]),
            Trip("b", route="21", stops=[Stop("S", T0 + timedelta(minutes=3))]),
        ],
    )
    snap = parse_trip_updates(feed, {"42"}, {"S"})
    assert [p.trip_id for p in snap.for_stop("S")] == ["a"]


def test_skipped_stop_is_not_a_prediction_but_is_recorded():
    feed = build_feed(T0, [Trip("a", stops=[Stop("S", skipped=True), Stop("N", T0)])])
    snap = parse_trip_updates(feed, {"40"}, {"S"})
    assert snap.for_stop("S") == []
    assert "S" in snap.trips["a"].skipped_stop_ids
    assert "S" not in snap.trips["a"].remaining_stop_ids


def test_canceled_trip_has_no_predictions():
    feed = build_feed(
        T0, [Trip("a", canceled=True, stops=[Stop("S", T0 + timedelta(minutes=5))])]
    )
    snap = parse_trip_updates(feed, {"40"}, {"S"})
    assert snap.for_stop("S") == []
    assert snap.trips["a"].canceled


def test_trip_without_vehicle_is_kept_with_no_vehicle():
    feed = build_feed(T0, [Trip("a", vehicle=None, stops=[Stop("S", T0)])])
    snap = parse_trip_updates(feed, {"40"}, {"S"})
    assert snap.for_stop("S")[0].vehicle_id is None


def test_stop_update_without_time_is_ignored():
    feed = build_feed(T0, [Trip("a", stops=[Stop("S", None)])])
    assert parse_trip_updates(feed, {"40"}, {"S"}).for_stop("S") == []


def test_invalid_protobuf_raises():
    with pytest.raises(TransitDataError):
        parse_trip_updates(b"<html>Service Unavailable</html>", {"40"}, {"S"})


def test_missing_header_timestamp_raises():
    with pytest.raises(TransitDataError):
        parse_trip_updates(b"", {"40"}, {"S"})


# --- BusSchedules --------------------------------------------------------------------------


def test_real_bus_schedules_fixture():
    payload = json.loads((FIX / "bus_schedules_40_22265.json").read_text())
    rows = parse_bus_schedules(payload, "40", "22265", NY)
    assert len(rows) == 6
    assert rows[0].trip_id == "964081"
    assert rows[0].direction_id == 1
    assert rows[0].scheduled == datetime(2026, 11, 18, 22, 24, tzinfo=UTC)  # 5:24 pm EST
    assert [r.scheduled for r in rows] == sorted(r.scheduled for r in rows)


def test_bus_schedules_skips_malformed_rows():
    payload = {
        "40": [
            {"Route": "40", "trip_id": "1", "Direction": "1", "DateCalender": "11/18/26 05:24 pm"},
            {"Route": "40", "trip_id": "2", "Direction": "1", "DateCalender": "garbage"},
            {"Route": "40", "Direction": "1"},
        ]
    }
    assert [r.trip_id for r in parse_bus_schedules(payload, "40", "S", NY)] == ["1"]


def test_bus_schedules_missing_route_is_empty():
    assert parse_bus_schedules({}, "40", "S", NY) == []


@pytest.mark.parametrize("payload", [[], "nope", {"40": "x"}])
def test_bus_schedules_invalid_shape_raises(payload):
    with pytest.raises(TransitDataError):
        parse_bus_schedules(payload, "40", "S", NY)


def test_local_time_across_midnight():
    late = parse_local_datetime("11/18/26 11:55 pm", NY)
    early = parse_local_datetime("11/19/26 12:05 am", NY)
    assert late == datetime(2026, 11, 19, 4, 55, tzinfo=UTC)
    assert early - late == timedelta(minutes=10)


def test_local_time_dst_spring_forward_and_fall_back():
    # Summer (EDT, UTC-4) vs winter (EST, UTC-5)
    assert parse_local_datetime("07/01/26 08:00 am", NY) == datetime(2026, 7, 1, 12, 0, tzinfo=UTC)
    assert parse_local_datetime("01/05/27 08:00 am", NY) == datetime(2027, 1, 5, 13, 0, tzinfo=UTC)
    # Fall back 2026-11-01: 1:30 am happens twice; we take the earlier (EDT) instant.
    assert parse_local_datetime("11/01/26 01:30 am", NY) == datetime(2026, 11, 1, 5, 30, tzinfo=UTC)
