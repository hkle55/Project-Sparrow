"""Prediction accuracy analysis.

Sign convention: error = predicted - actual (seconds).
    error > 0  -> the bus arrived EARLIER than predicted (the dangerous direction)
    error < 0  -> the bus arrived later than predicted

Ground truth, never mixed:
- "observed": manual observations (independent of SEPTA)
- "inferred": arrival window from SEPTA GPS vehicle positions (last report before the stop to
  first report at/after it). Independent of SEPTA's *prediction* system, but still SEPTA data.
SEPTA's own last prediction, and the time the stop drops out of trip updates, are never used
as truth.
"""

from __future__ import annotations

import math
import sqlite3
import statistics
from bisect import bisect_right
from collections import defaultdict
from dataclasses import dataclass, field

LEADS_MIN = (2, 5, 10, 15)
POLL_GAP_S = 90  # a prediction "at time t" needs a successful poll in [t - 90 s, t]
MATCH_WINDOW_S = 600  # manual observation must be within 10 min of a trip's expected arrival
MAX_BRACKET_S = 180  # wider GPS brackets are too uncertain to count as inferred arrivals


@dataclass(frozen=True)
class Truth:
    trip_id: str
    service_date: str
    stop_id: str
    route: str
    at: float
    source: str  # "observed" | "inferred"
    uncertainty_s: float  # +/- around `at`


@dataclass
class TripStop:
    trip_id: str
    service_date: str
    stop_id: str
    route: str
    stop_sequence: int | None
    vehicle_id: str | None
    first_listed: float
    last_listed: float
    dropped_at: float | None
    predictions: list[tuple[float, float, float]] = field(default_factory=list)
    # (observed_at, predicted_at, feed_ts)


def percentile(values: list[float], q: float) -> float:
    """Linear-interpolated percentile, q in [0, 100]."""
    if not values:
        return math.nan
    s = sorted(values)
    k = (len(s) - 1) * q / 100
    lo, hi = math.floor(k), math.ceil(k)
    return s[lo] + (s[hi] - s[lo]) * (k - lo)


def infer_from_vehicle(
    samples: list[sqlite3.Row | dict], target_seq: int
) -> tuple[float, float] | None:
    """Return (midpoint, half_width) of the arrival window at `target_seq`, or None.

    SEPTA semantics (verified 2026-11-18): IN_TRANSIT_TO N = heading to stop N;
    STOPPED_AT N = stop N is the last stop reached (trip updates then list N+1).
    """
    last_before = None
    for s in sorted(samples, key=lambda s: s["reported_at"]):
        seq = s["stop_sequence"]
        if seq is None:
            continue
        reached = seq > target_seq or (seq == target_seq and s["status"] == "STOPPED_AT")
        if not reached:
            last_before = s["reported_at"]
            continue
        if last_before is None:
            return None  # first sample already past the stop: no lower bound
        width = s["reported_at"] - last_before
        if width > MAX_BRACKET_S:
            return None
        return (last_before + s["reported_at"]) / 2, width / 2
    return None


def load_trip_stops(conn: sqlite3.Connection) -> dict[tuple[str, str, str], TripStop]:
    out: dict[tuple[str, str, str], TripStop] = {}
    for r in conn.execute("SELECT * FROM trip_stops"):
        out[(r["trip_id"], r["service_date"], r["stop_id"])] = TripStop(
            r["trip_id"], r["service_date"], r["stop_id"], r["route"], r["stop_sequence"],
            r["vehicle_id"], r["first_listed"], r["last_listed"], r["dropped_at"],
        )
    for r in conn.execute(
        "SELECT trip_id, service_date, stop_id, observed_at, predicted_at, feed_ts"
        " FROM predictions ORDER BY observed_at"
    ):
        ts = out.get((r["trip_id"], r["service_date"], r["stop_id"]))
        if ts is not None:
            ts.predictions.append((r["observed_at"], r["predicted_at"], r["feed_ts"]))
    return out


def inferred_truths(
    conn: sqlite3.Connection, trip_stops: dict[tuple[str, str, str], TripStop]
) -> list[Truth]:
    samples: dict[tuple[str, str], list] = defaultdict(list)
    for r in conn.execute("SELECT * FROM vehicle_samples"):
        samples[(r["trip_id"], r["service_date"])].append(r)
    out = []
    for ts in trip_stops.values():
        if ts.stop_sequence is None:
            continue
        got = infer_from_vehicle(samples.get((ts.trip_id, ts.service_date), []), ts.stop_sequence)
        if got:
            out.append(Truth(ts.trip_id, ts.service_date, ts.stop_id, ts.route, got[0],
                             "inferred", got[1]))
    return out


def observed_truths(
    conn: sqlite3.Connection,
    trip_stops: dict[tuple[str, str, str], TripStop],
    inferred: list[Truth],
) -> tuple[list[Truth], int]:
    """Match manual observations to trips. Returns (truths, unmatched_count)."""
    inferred_at = {(t.trip_id, t.service_date, t.stop_id): t.at for t in inferred}
    out, unmatched = [], 0
    for ob in conn.execute("SELECT * FROM observations ORDER BY arrived_at"):
        best, best_d = None, None
        for key, ts in trip_stops.items():
            if ts.route != ob["route"] or ts.stop_id != ob["stop_id"]:
                continue
            if ob["vehicle_id"] and ts.vehicle_id and ob["vehicle_id"] != ts.vehicle_id:
                continue
            ref = inferred_at.get(key) or (ts.predictions[-1][1] if ts.predictions else None)
            if ref is None:
                continue
            d = abs(ref - ob["arrived_at"])
            if d <= MATCH_WINDOW_S and (best_d is None or d < best_d):
                best, best_d = ts, d
        if best is None:
            unmatched += 1
            continue
        out.append(Truth(best.trip_id, best.service_date, best.stop_id, best.route,
                         ob["arrived_at"], "observed", 30.0))
    return out, unmatched


def polls_ok_times(conn: sqlite3.Connection) -> list[float]:
    return [r[0] for r in conn.execute(
        "SELECT observed_at FROM polls WHERE tu_error IS NULL ORDER BY observed_at")]


def prediction_at(ts: TripStop, t: float, ok_polls: list[float]) -> float | None:
    """SEPTA's prediction in effect at time t, if we were actually watching then."""
    i = bisect_right(ok_polls, t)
    if i == 0 or t - ok_polls[i - 1] > POLL_GAP_S:
        return None  # collector wasn't running / feed failing at t
    if t < ts.first_listed or t > ts.last_listed:
        return None
    times = [p[0] for p in ts.predictions]
    j = bisect_right(times, t)
    return ts.predictions[j - 1][1] if j else None


@dataclass
class LeadStats:
    source: str
    lead_min: int
    n: int
    mae_s: float
    median_s: float
    early_rate: float  # share arriving earlier than predicted
    early_over_60_rate: float
    p90_s: float
    p95_s: float
    miss_rate: float  # share arriving more than the buffer earlier than predicted


def lead_stats(
    truths: list[Truth],
    trip_stops: dict[tuple[str, str, str], TripStop],
    ok_polls: list[float],
    buffer_s: float,
) -> list[LeadStats]:
    out = []
    for source in ("observed", "inferred"):
        for lead in LEADS_MIN:
            errors = []
            for tr in truths:
                if tr.source != source:
                    continue
                ts = trip_stops.get((tr.trip_id, tr.service_date, tr.stop_id))
                if ts is None:
                    continue
                p = prediction_at(ts, tr.at - lead * 60, ok_polls)
                if p is not None:
                    errors.append(p - tr.at)
            n = len(errors)
            out.append(LeadStats(
                source, lead, n,
                mae_s=statistics.fmean(abs(e) for e in errors) if n else math.nan,
                median_s=statistics.median(errors) if n else math.nan,
                early_rate=sum(e > 0 for e in errors) / n if n else math.nan,
                early_over_60_rate=sum(e > 60 for e in errors) / n if n else math.nan,
                p90_s=percentile(errors, 90),
                p95_s=percentile(errors, 95),
                miss_rate=sum(e > buffer_s for e in errors) / n if n else math.nan,
            ))
    return out


@dataclass
class RevisionStats:
    trips: int
    median_revisions: float
    max_revisions: int
    median_total_change_s: float
    largest_earlier_jump_s: float  # biggest single move of a prediction earlier


def revision_stats(trip_stops: dict[tuple[str, str, str], TripStop]) -> RevisionStats:
    counts, totals, jumps = [], [], [0.0]
    for ts in trip_stops.values():
        # Only the last 20 minutes before the bus reached the stop matter for leaving. The
        # prediction already in effect when that window opened is the baseline.
        start = ts.last_listed - 1200
        before = [p for p in ts.predictions if p[0] < start]
        window = before[-1:] + [p for p in ts.predictions if p[0] >= start]
        if not window:
            continue
        values = [p[1] for p in window]
        diffs = [b - a for a, b in zip(values, values[1:], strict=False)]
        counts.append(len(diffs))
        totals.append(sum(abs(d) for d in diffs))
        jumps.extend(-d for d in diffs if d < 0)
    return RevisionStats(
        trips=len(counts),
        median_revisions=statistics.median(counts) if counts else math.nan,
        max_revisions=max(counts, default=0),
        median_total_change_s=statistics.median(totals) if totals else math.nan,
        largest_earlier_jump_s=max(jumps),
    )


@dataclass
class FreshnessStats:
    polls: int
    failed_rate: float
    age_p50_s: float
    age_p95_s: float
    age_max_s: float
    stale_rate: float  # share of successful polls whose feed was older than stale_after_s
    first_poll: float | None
    last_poll: float | None


def freshness_stats(conn: sqlite3.Connection, stale_after_s: float) -> FreshnessStats:
    rows = conn.execute("SELECT observed_at, tu_feed_ts, tu_error FROM polls").fetchall()
    ages = [r["observed_at"] - r["tu_feed_ts"] for r in rows
            if r["tu_error"] is None and r["tu_feed_ts"] is not None]
    n = len(rows)
    return FreshnessStats(
        polls=n,
        failed_rate=sum(r["tu_error"] is not None for r in rows) / n if n else math.nan,
        age_p50_s=percentile(ages, 50),
        age_p95_s=percentile(ages, 95),
        age_max_s=max(ages, default=math.nan),
        stale_rate=sum(a > stale_after_s for a in ages) / len(ages) if ages else math.nan,
        first_poll=min((r["observed_at"] for r in rows), default=None),
        last_poll=max((r["observed_at"] for r in rows), default=None),
    )


@dataclass
class Analysis:
    leads: list[LeadStats]
    revisions: RevisionStats
    freshness: FreshnessStats
    trips_tracked: int
    inferred_count: int
    observed_count: int
    unmatched_observations: int
    missing_prediction_count: int  # inferred arrivals with no prediction 5 min before
    buffer_s: float


def analyze(conn: sqlite3.Connection, buffer_s: float, stale_after_s: float) -> Analysis:
    trip_stops = load_trip_stops(conn)
    inferred = inferred_truths(conn, trip_stops)
    observed, unmatched = observed_truths(conn, trip_stops, inferred)
    ok_polls = polls_ok_times(conn)
    missing = sum(
        1 for tr in inferred
        if prediction_at(trip_stops[(tr.trip_id, tr.service_date, tr.stop_id)],
                         tr.at - 300, ok_polls) is None
    )
    return Analysis(
        leads=lead_stats(inferred + observed, trip_stops, ok_polls, buffer_s),
        revisions=revision_stats(trip_stops),
        freshness=freshness_stats(conn, stale_after_s),
        trips_tracked=len(trip_stops),
        inferred_count=len(inferred),
        observed_count=len(observed),
        unmatched_observations=unmatched,
        missing_prediction_count=missing,
        buffer_s=buffer_s,
    )
