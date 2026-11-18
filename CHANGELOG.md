# Changelog

All notable changes, grouped by milestone. Dates are in America/New_York.

## Unreleased

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
