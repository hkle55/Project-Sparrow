"""Render an Analysis as a readable Markdown report."""

from __future__ import annotations

import math
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from .analysis import Analysis, LeadStats

MIN_SAMPLE = 30  # below this, no conclusions about the buffer


def _s(v: float) -> str:
    return "—" if v is None or (isinstance(v, float) and math.isnan(v)) else f"{v:+.0f}s"


def _abs(v: float) -> str:
    return "—" if math.isnan(v) else f"{v:.0f}s"


def _pct(v: float) -> str:
    return "—" if math.isnan(v) else f"{v * 100:.0f}%"


def _when(ts: float | None, tz: ZoneInfo) -> str:
    return datetime.fromtimestamp(ts, UTC).astimezone(tz).strftime("%Y-%m-%d %H:%M") if ts else "—"


def buffer_verdict(a: Analysis) -> str:
    """Judge the buffer at 5 and 10 min leads (when she'd be deciding to leave)."""
    rows = [s for s in a.leads if s.lead_min in (5, 10) and s.n > 0]
    best = {}
    for s in rows:  # prefer independent observations when there are enough of them
        if s.source == "observed" and s.n >= MIN_SAMPLE:
            best[s.lead_min] = s
        elif s.lead_min not in best:
            best[s.lead_min] = s
    if not best or all(s.n < MIN_SAMPLE for s in best.values()):
        n = max((s.n for s in best.values()), default=0)
        return (f"**Not enough data yet** ({n} arrivals at best; need at least {MIN_SAMPLE} "
                "per lead time). No conclusion about the buffer.")
    lines = []
    for lead, s in sorted(best.items()):
        if s.n < MIN_SAMPLE:
            continue
        need = max(0.0, s.p95_s)
        ok = s.miss_rate <= 0.05
        lines.append(
            f"- {lead} min ahead ({s.source}, n={s.n}): {_pct(s.miss_rate)} of buses came more "
            f"than the {a.buffer_s / 60:.0f}-min buffer early → "
            + ("**buffer sufficient** (≤5% misses)." if ok
               else f"**buffer too small**; ~{math.ceil(need / 60)} min covers 95%.")
        )
    return "\n".join(lines)


def _lead_table(rows: list[LeadStats]) -> str:
    out = [
        "| Lead | n | Mean abs error | Median error | Early (any) | Early >60s | "
        "P90 | P95 | Beat buffer |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for s in rows:
        out.append(
            f"| {s.lead_min} min | {s.n} | {_abs(s.mae_s)} | {_s(s.median_s)} | "
            f"{_pct(s.early_rate)} | {_pct(s.early_over_60_rate)} | {_s(s.p90_s)} | "
            f"{_s(s.p95_s)} | {_pct(s.miss_rate)} |"
        )
    return "\n".join(out)


def render(a: Analysis, tz: ZoneInfo, generated_at: datetime) -> str:
    f, r = a.freshness, a.revisions
    observed = [s for s in a.leads if s.source == "observed"]
    inferred = [s for s in a.leads if s.source == "inferred"]
    return f"""# Sparrow prediction validation report

Generated {generated_at.astimezone(tz).strftime("%Y-%m-%d %H:%M %Z")}.
Collection window: {_when(f.first_poll, tz)} → {_when(f.last_poll, tz)} ({f.polls} polls).

**Error = predicted − actual.** Positive means the bus came *earlier* than SEPTA predicted
(the dangerous direction). "Beat buffer" = bus came more than the
{a.buffer_s / 60:.0f}-min safety buffer earlier than predicted, so following Sparrow you
would have missed it.

## Is the {a.buffer_s / 60:.0f}-minute buffer enough?

{buffer_verdict(a)}

## Accuracy vs independently observed arrivals (manual)

{a.observed_count} observed arrivals matched ({a.unmatched_observations} unmatched).

{_lead_table(observed)}

## Accuracy vs inferred arrivals (SEPTA GPS vehicle positions)

{a.inferred_count} arrivals inferred from vehicle positions. Each is the midpoint of the gap
between the last GPS report before the stop and the first at or after it. These come from
SEPTA's data, so they aren't independent of SEPTA, but they don't come from its predictions.

{_lead_table(inferred)}

## Prediction revisions (final 20 min before each bus reached the stop)

- Trips: {r.trips}
- Median revisions per trip: {r.median_revisions if not math.isnan(r.median_revisions) else "—"}
  (max {r.max_revisions})
- Median total movement: {_abs(r.median_total_change_s)}
- Largest single jump *earlier*: {_abs(r.largest_earlier_jump_s)}

## Data freshness

- Failed fetches: {_pct(f.failed_rate)}
- Feed age at poll: median {_abs(f.age_p50_s)}, P95 {_abs(f.age_p95_s)}, max {_abs(f.age_max_s)}
- Polls with stale data: {_pct(f.stale_rate)}
- Inferred arrivals with no prediction 5 min before: {a.missing_prediction_count}
  of {a.inferred_count}

## Caveats

- Small samples are noisy. Treat any lead time with n < {MIN_SAMPLE} as anecdotal.
- Inferred arrival windows are typically ±15 s. Manual observations are assumed ±30 s.
- Trips tracked overall: {a.trips_tracked}.
"""
