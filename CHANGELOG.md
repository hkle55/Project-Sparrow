# Changelog

All notable changes, grouped by milestone. Dates are in America/New_York.

## Unreleased

### Milestone 4: Prediction validation
- Collector logs prediction changes, poll freshness, and GPS vehicle positions to SQLite
  (`data/`, gitignored). Runs in-app (`SPARROW_COLLECT=1`) or via `scripts/collect.py`.
- Accuracy analysis at 2/5/10/15-min leads against manual observations and GPS-inferred
  arrivals, kept separate. SEPTA's own final prediction is never used as truth.
- `/observe` phone page for manual arrival taps (offline queue, undo), observation API,
  Markdown report at `/api/v1/validation/report` and `scripts/validation_report.py`.
- Optional `SPARROW_ACCESS_TOKEN` protects every route except `/health`.

### TIGHT CONNECTION state
- Buses reachable only by cutting into the safety buffer are recommended as TIGHT (with the
  safer bus shown) only when no safe bus boards within `tight_max_wait_min` (10) after them.

### Milestone 3: Web device simulator
- Static HTML/CSS/JS simulator served at `/`: big route and countdown, 3 arrivals per
  route, live/stale/scheduled badges, freshness, and a NO CONNECTION state.
- Local 1 s countdown with server clock-skew correction. Polls every 15 s.
- Simulation mode (8 scenarios) with a persistent "SIMULATION" banner.

### Milestone 2: Recommendation engine and API
- Pure departure engine (walk + buffer, ok/tight/missed, floored countdowns).
- Route preference with a configurable threshold.
- `GET /api/v1/commute/{mode}` compact JSON, plus `/modes`, `/scenarios`, `/health`.

### Milestone 1: SEPTA data
- GTFS-RT trip-updates and BusSchedules parsers. Cached client with retries and
  last-good fallback.
- Live/scheduled merge with passed, canceled, and detour handling and staleness labels.
- `scripts/next_arrivals.py`, `scripts/find_stops.py`. Real response fixtures.

### Milestone 0: Project initialization
- Backend skeleton (FastAPI) with pinned dependencies.
- GitHub Actions CI: ruff lint and offline unit tests.
- Project docs: README, PROJECT_PLAN, CLAUDE.md, transit research notes.
