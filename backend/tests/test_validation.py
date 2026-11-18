"""Prediction-validation pipeline: collector -> SQLite -> inference -> analysis -> report."""

import math
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from app.config import RouteOption
from app.transit.gtfs_rt import parse_trip_updates, parse_vehicle_positions
from app.validation import store
from app.validation.analysis import (
    analyze,
    infer_from_vehicle,
    load_trip_stops,
    percentile,
    polls_ok_times,
    prediction_at,
)
from app.validation.collector import record
from app.validation.report import render
from tests.feedbuilder import Stop, Trip, Vehicle, build_feed, build_vehicle_feed

A = datetime(2026, 11, 18, 22, 0, tzinfo=UTC)  # true arrival at stop S
OPT = RouteOption("40", 1, "S", "Test St", 4)
NY = ZoneInfo("America/New_York")


def predicted_for(t: datetime) -> datetime:
    """SEPTA predicts 90 s late until 3 min out, then 10 s late."""
    return A + timedelta(seconds=90 if t < A - timedelta(minutes=3) else 10)


def poll(conn, t: datetime, *, tu_ok=True, header_lag=20):
    trips = []
    if t <= A + timedelta(seconds=30):  # trip updates linger ~30 s after arrival
        trips.append(Trip("T1", stops=[Stop("S", predicted_for(t), seq=10),
                                       Stop("N", predicted_for(t) + timedelta(minutes=1), seq=11)],
                          vehicle="3381"))
    else:
        trips.append(Trip("T1", stops=[Stop("N", A + timedelta(minutes=1), seq=11)],
                          vehicle="3381"))
    # same route, other direction: must be ignored
    trips.append(Trip("X9", direction_id=0, stops=[Stop("S", t + timedelta(minutes=2))]))
    header = t - timedelta(seconds=header_lag)
    tu = parse_trip_updates(build_feed(header, trips), {"40"}, {"S"})
    status = "STOPPED_AT" if t >= A else "IN_TRANSIT_TO"
    vp = parse_vehicle_positions(
        build_vehicle_feed(header, [Vehicle("T1", 10, t, status=status, vehicle="3381")]), {"40"}
    )
    record(conn, [OPT], t, tu if tu_ok else None, vp, None if tu_ok else "ConnectTimeout")


@pytest.fixture
def db():
    conn = store.connect(":memory:")
    t = A - timedelta(minutes=20)
    while t <= A + timedelta(minutes=3):
        poll(conn, t)
        t += timedelta(seconds=30)
    return conn


# --- collector ----------------------------------------------------------------------------


def test_predictions_stored_only_on_change(db):
    rows = db.execute("SELECT predicted_at FROM predictions WHERE trip_id='T1'").fetchall()
    assert [r[0] for r in rows] == [
        (A + timedelta(seconds=90)).timestamp(),
        (A + timedelta(seconds=10)).timestamp(),
    ]


def test_wrong_direction_not_recorded(db):
    assert db.execute("SELECT COUNT(*) FROM predictions WHERE trip_id='X9'").fetchone()[0] == 0


def test_trip_stop_lifecycle_and_drop_detection(db):
    r = db.execute("SELECT * FROM trip_stops WHERE trip_id='T1'").fetchone()
    assert r["stop_sequence"] == 10 and r["vehicle_id"] == "3381"
    assert r["last_listed"] == (A + timedelta(seconds=30)).timestamp()
    assert r["dropped_at"] == (A + timedelta(seconds=60)).timestamp()


def test_vehicle_samples_deduplicated(db):
    n = db.execute("SELECT COUNT(*) FROM vehicle_samples").fetchone()[0]
    polls = db.execute("SELECT COUNT(*) FROM polls").fetchone()[0]
    assert n == polls  # one distinct GPS timestamp per poll here
    t = A + timedelta(minutes=3)
    vp = parse_vehicle_positions(
        build_vehicle_feed(t, [Vehicle("T1", 10, t, status="STOPPED_AT", vehicle="3381")]), {"40"}
    )
    record(db, [OPT], t + timedelta(seconds=5), None, vp)
    assert db.execute("SELECT COUNT(*) FROM vehicle_samples").fetchone()[0] == n


def test_failed_poll_recorded_without_predictions():
    conn = store.connect(":memory:")
    poll(conn, A - timedelta(minutes=5), tu_ok=False)
    assert conn.execute("SELECT tu_error FROM polls").fetchone()[0] == "ConnectTimeout"
    assert conn.execute("SELECT COUNT(*) FROM predictions").fetchone()[0] == 0


# --- inference ----------------------------------------------------------------------------


def s(t, seq, status="IN_TRANSIT_TO"):
    return {"reported_at": t, "stop_sequence": seq, "status": status}


def test_infer_bracket_midpoint():
    got = infer_from_vehicle([s(100, 9), s(130, 10), s(160, 10, "STOPPED_AT"), s(190, 11)], 10)
    assert got == (145, 15)


def test_infer_bus_skips_past_stop_between_reports():
    assert infer_from_vehicle([s(100, 8), s(140, 12)], 10) == (120, 20)


def test_infer_needs_a_report_before_the_stop():
    assert infer_from_vehicle([s(100, 10, "STOPPED_AT"), s(130, 11)], 10) is None


def test_infer_rejects_wide_brackets():
    assert infer_from_vehicle([s(100, 9), s(400, 11)], 10) is None


def test_infer_not_yet_arrived():
    assert infer_from_vehicle([s(100, 8), s(130, 9)], 10) is None


def test_inferred_arrival_from_collected_data(db):
    a = analyze(db, buffer_s=120, stale_after_s=120)
    assert a.inferred_count == 1
    # bracket [A-30s, A] -> midpoint A-15s


def test_prediction_at_respects_polling_gaps(db):
    ts = load_trip_stops(db)[("T1", "20261118", "S")]
    ok = polls_ok_times(db)
    assert prediction_at(ts, (A - timedelta(minutes=5)).timestamp(), ok) == (
        A + timedelta(seconds=90)
    ).timestamp()
    # before collection started -> unknown, not guessed
    assert prediction_at(ts, (A - timedelta(minutes=30)).timestamp(), ok) is None
    # with a 5-minute hole in polling, the prediction at that time is unknown
    holey = [x for x in ok if not (A - timedelta(minutes=10)).timestamp() < x
             < (A - timedelta(minutes=5)).timestamp()]
    assert prediction_at(ts, (A - timedelta(minutes=6)).timestamp(), holey) is None


# --- analysis -----------------------------------------------------------------------------


def observe(conn, at, vehicle="3381"):
    store.add_observation(conn, recorded_at=at.timestamp(), arrived_at=at.timestamp(),
                          route="40", stop_id="S", vehicle_id=vehicle)


def test_lead_errors_against_manual_observation(db):
    observe(db, A)
    a = analyze(db, buffer_s=120, stale_after_s=120)
    assert a.observed_count == 1 and a.unmatched_observations == 0
    by_lead = {s.lead_min: s for s in a.leads if s.source == "observed"}
    assert by_lead[2].median_s == 10  # 2 min out SEPTA said A+10
    assert by_lead[5].median_s == 90  # 5 min out SEPTA said A+90 -> bus 90 s early
    assert by_lead[15].mae_s == 90
    assert by_lead[5].early_rate == 1.0 and by_lead[5].miss_rate == 0.0  # 90 s < 2-min buffer
    assert analyze(db, buffer_s=60, stale_after_s=120).leads[1].miss_rate == 1.0


def test_inferred_and_observed_reported_separately(db):
    observe(db, A)
    a = analyze(db, buffer_s=120, stale_after_s=120)
    inferred5 = next(s for s in a.leads if s.source == "inferred" and s.lead_min == 5)
    observed5 = next(s for s in a.leads if s.source == "observed" and s.lead_min == 5)
    assert inferred5.n == 1 and observed5.n == 1
    assert inferred5.median_s == 105  # inferred A-15 vs prediction A+90


def test_observation_with_wrong_bus_number_not_matched(db):
    observe(db, A, vehicle="9999")
    assert analyze(db, 120, 120).unmatched_observations == 1


def test_observation_far_from_any_trip_not_matched(db):
    observe(db, A + timedelta(hours=2))
    assert analyze(db, 120, 120).observed_count == 0


def test_revisions(db):
    r = analyze(db, 120, 120).revisions
    assert r.trips == 1 and r.median_revisions == 1
    assert r.largest_earlier_jump_s == 80


def test_freshness(db):
    poll(db, A + timedelta(minutes=4), tu_ok=False)
    poll(db, A + timedelta(minutes=5), header_lag=300)
    f = analyze(db, 120, 120).freshness
    assert f.age_p50_s == 20 and f.age_max_s == 300
    assert 0 < f.failed_rate < 0.05 and 0 < f.stale_rate < 0.05


def test_percentile():
    assert percentile([1, 2, 3, 4], 50) == 2.5
    assert percentile([5], 95) == 5
    assert math.isnan(percentile([], 90))


# --- report -------------------------------------------------------------------------------


def test_report_withholds_verdict_on_small_samples(db):
    observe(db, A)
    text = render(analyze(db, 120, 120), NY, A)
    assert "Not enough data yet" in text
    assert "| 5 min | 1 |" in text
    assert "SEPTA GPS vehicle positions" in text


def test_report_verdict_with_enough_data():
    conn = store.connect(":memory:")
    # 40 trips, each predicted 150 s late 5-10 min out -> buses 2.5 min early: beats a 2-min buffer
    for i in range(40):
        base = A + timedelta(minutes=30 * i)
        trip = f"T{i}"
        t = base - timedelta(minutes=12)
        while t <= base + timedelta(seconds=60):
            listed = t <= base
            stops = [Stop("S", base + timedelta(seconds=150), seq=10)] if listed else []
            stops.append(Stop("N", base + timedelta(minutes=1), seq=11))
            tu = parse_trip_updates(build_feed(t, [Trip(trip, stops=stops)]), {"40"}, {"S"})
            vp = parse_vehicle_positions(build_vehicle_feed(t, [Vehicle(
                trip, 10, t, status="STOPPED_AT" if t >= base else "IN_TRANSIT_TO")]), {"40"})
            record(conn, [OPT], t, tu, vp)
            t += timedelta(seconds=30)
    text = render(analyze(conn, 120, 120), NY, A)
    assert "buffer too small" in text
    assert "~3 min covers 95%" in text
