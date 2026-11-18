# Handoff

_Last updated: 2026-11-18, Milestone 4 tooling done, Milestone 5 prepared._

## Status

- M0–M3: done. Local web prototype on live SEPTA data.
- TIGHT CONNECTION state: done (PR #5).
- M4 prediction validation: **tooling done** (PR #6). Collector, GPS-inferred arrivals, `/observe`
  manual logging, accuracy report. **Data collection hasn't really started**: it needs
  hosting to run 24/7, plus her manual observations.
- M5 deployment: **prepared, not deployed** (PR #7). Recommendation is Fly.io always-on at
  ~$2–3/mo. Waiting on the owner's approval to spend money.
- Return commute: unconfigured by owner decision.
- Hardware: not started by owner decision.

## Environment

- Cloud environment `project-sparrow`: the setup script creates `.venv` with dev dependencies,
  and `SPARROW_CONFIG_JSON` holds the real profile. Verified from a fresh session
  2026-11-18 (see final report in the PR #7 thread / session).
- Validation DB: `data/sparrow.sqlite` (gitignored, container-local, lost when the container is
  reclaimed). Real collection belongs on the hosted instance.

## Tests

- `cd backend && ../.venv/bin/pytest -q`: 144 passed (offline)
- `pytest -m live`: passes against SEPTA
- `ruff check . ../scripts`: clean
- CI: lint + tests + Docker image build and smoke test

## Owner decisions pending

1. Approve hosting spend (Fly.io ~$2–3/mo, or Railway $5), then create the account (steps in
   docs/deployment.md).
2. Return commute stop and walking time, when known.

## Next steps

1. After approval: deploy, set the access token, and give her the `?key=` link and the `/observe`
   bookmark.
2. Let it collect for 2+ weeks. Ask for 30+ manual observations across both routes and
   different times of day.
3. Run the report. Adjust `safety_buffer_min` if the P95 early error says so.
4. Then M6 hardware research (no purchases without approval).
