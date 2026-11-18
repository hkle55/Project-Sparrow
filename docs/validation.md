# Prediction validation (Milestone 4)

Goal: find out whether SEPTA's predictions are good enough, and whether the 2-minute safety
buffer actually protects against early buses, **before** building hardware.

## How it works

1. **Collector** (every 30 s, in-app with `SPARROW_COLLECT=1` or `scripts/collect.py`):
   - Logs SEPTA's predicted arrival for each trip at each configured stop, but only when the
     prediction *changes*. The value in effect at any moment is the last change before it.
   - Logs every poll: success or failure, and the feed's age.
   - Logs GPS vehicle positions for trips on the watched routes.
   - Records when a stop drops out of a trip's update (diagnostic only).
2. **Ground truth**, kept strictly separate:
   - **Observed**: manual taps on `/observe` (or `scripts/observe.py`). This is the only truly
     independent source.
   - **Inferred**: the arrival window from GPS vehicle positions, between the last report
     before the stop and the first at or after it. Windows wider than 3 min are discarded.
     Typical width is 15–30 s, and the midpoint is used.
   - **Never truth**: SEPTA's last prediction, or the moment the stop drops out of trip
     updates. Both come from the prediction system being tested.
3. **Analysis** (`scripts/validation_report.py` or `GET /api/v1/validation/report`): for each
   arrival and lead time L ∈ {2, 5, 10, 15} min, it takes the prediction in effect at
   `arrival − L` (only if the collector had a successful poll within the previous 90 s) and
   computes `error = predicted − actual`.

### SEPTA vehicle-position semantics (verified 2026-11-18)

- `IN_TRANSIT_TO N` = heading to stop sequence N.
- `STOPPED_AT N` = N is the last stop reached. It's reported most of the time, even while
  the bus is moving, and trip updates then list N+1 as the next stop.
- Trip updates keep listing a stop for up to about a minute after the bus reaches it, with
  a past arrival time.

## Metrics

| Metric | Meaning |
|---|---|
| Mean absolute error | Typical size of the miss, either direction |
| Median error | Bias. Positive = buses tend to be earlier than predicted |
| Early (any) / Early >60 s | How often the bus beats the prediction |
| P90 / P95 | 90% / 95% of buses arrive no more than this much earlier than predicted |
| Beat buffer | Share of buses earlier than predicted by more than the safety buffer. These are the ones you'd miss following Sparrow |
| Revisions | How much predictions move in the final 20 min, and the biggest single jump earlier |
| Freshness | Failed fetches, feed age distribution, share of stale polls |

**Buffer verdict:** at the 5- and 10-minute leads (when she'd decide to leave), the buffer
is called sufficient if ≤5% of buses beat it. Otherwise the report suggests the buffer
that covers 95% (P95). With fewer than 30 arrivals per lead time, the report says *not
enough data* and draws no conclusion.

## Recording observations

On the phone, open `/observe` (bookmark it). Tap **40 ARRIVED** or **42 ARRIVED** when the bus
reaches the stop. Optionally type the fleet number (painted on the bus) first, and use "It
arrived … ago" if you're late tapping. Taps use the phone's clock. If there's no
connection, the tap is saved on the phone and uploaded later. Mistakes can be undone from
the Recent list.

Observations match a tracked trip at the same stop within ±10 min, by bus number if given.
Unmatched observations are counted in the report.

## Running it

```bash
.venv/bin/python scripts/collect.py --once   # smoke test
.venv/bin/python scripts/collect.py          # run until Ctrl-C
.venv/bin/python scripts/validation_report.py
```

The data lives in `data/sparrow.sqlite` (gitignored, private). It grows by roughly
5–10 MB/day for two routes. To be meaningful, collection must run continuously,
which is why it needs hosting (M5).

## Limits

- Inferred arrivals come from SEPTA's AVL (GPS) system. They're independent of the
  prediction model, but not of SEPTA.
- Manual observations are assumed accurate to ±30 s.
- Analysis is per arrival and doesn't weight by time of day. Rush hour may differ.
