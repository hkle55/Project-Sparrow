# Project Sparrow: notes for Claude Code sessions

Sparrow is a pocket transit companion for one SEPTA bus commuter in Philadelphia. It
answers: which bus, when it arrives, and when to leave. The backend does all the transit
work. The web UI is a thin client. **Accuracy beats
features**: never present scheduled, estimated, stale, or simulated data as live.

Start every session by reading `docs/handoff.md`, then `PROJECT_PLAN.md`.

**Status: complete.** The hosted web app is the product; the physical device was dropped
(firmware branches kept, unmerged). `mode=auto` shows the work commute in the morning and
home after `settings.home_after` (default 14:00 ET). The web app starts in auto; Switch mode
overrides it. Merges to `main` auto-deploy to Fly.io after CI passes.

## Layout

- `backend/app/transit/`: SEPTA adapters (GTFS-RT trip updates, BusSchedules JSON) and the cached fetcher
- `backend/app/predictions/`: merges live and scheduled data into classified arrivals
- `backend/app/recommendations/`: pure, deterministic departure and route-choice engine
- `backend/app/api/`: FastAPI app (`/health`, `/api/v1/commute/{mode}`, compact `/api/v1/device`,
  observations, report), serves `frontend/`
- `backend/app/validation/`: prediction logging (SQLite), GPS-inferred arrivals, accuracy analysis and report
- `backend/app/config.py`: loads the TOML commute profile
- `frontend/`: plain HTML/CSS/JS. `index.html` is the web simulator, `device.html` is a pixel preview
  of the physical screen (from `/api/v1/device`), and `observe.html` is manual arrival logging
- `config/commute.example.toml`: public example profile. The real one comes from `$SPARROW_CONFIG_JSON`
  (set on the `project-sparrow` cloud environment), `$SPARROW_CONFIG_TOML`, or `config/commute.local.toml` (gitignored)
- `Dockerfile`, `fly.toml`, `.github/workflows/deploy.yml`: hosting on Fly.io (live; see docs/deployment.md)
- `scripts/`: CLI tools (`next_arrivals.py`, `find_stops.py`)
- `docs/`: `transit-research.md`, `architecture.md`, `handoff.md`

## Commands (run from `backend/`)

```bash
python -m venv ../.venv && ../.venv/bin/pip install -r requirements-dev.txt
../.venv/bin/pytest -q              # unit tests, no network
../.venv/bin/pytest -m live -q      # live SEPTA integration tests
../.venv/bin/ruff check .
../.venv/bin/uvicorn app.api.main:app --reload   # http://127.0.0.1:8000
../.venv/bin/python ../scripts/next_arrivals.py   # terminal view of next buses
SPARROW_COLLECT=1 ../.venv/bin/uvicorn app.api.main:app   # also logs predictions to data/
../.venv/bin/python ../scripts/validation_report.py
```

The `project-sparrow` cloud environment's setup script creates `.venv` with all dev
dependencies, and sets `SPARROW_CONFIG_JSON` to the real profile. Nothing needs installing
by hand in a fresh session.

## Conventions

- Python 3.12+, type hints, small modules, and minimal dependencies. Ask before adding
  big ones.
- Internally, all times are timezone-aware UTC `datetime`s or epoch seconds. Convert to
  America/New_York only for display. Never round before deciding: floor countdowns so the
  display never shows more time than there really is.
- The recommendation engine is pure. It takes `now` as a parameter and does no I/O.
- Unit tests use fixtures in `backend/tests/fixtures/` and must never hit the network.
  Mark live tests `@pytest.mark.live`.
- Conventional Commits. Make small, coherent commits and stage files explicitly.

## Git workflow

- `main` is stable. Work on `feat/<topic>` or `fix/<topic>` branches. **Never** name a
  branch `claude/...`.
- Open a PR for each milestone and merge when CI is green.
- No force pushes, no history rewrites, and no deleting branches with unmerged work.
- Never add Claude attribution lines (Co-Authored-By, session links) to commits or PRs.

## Privacy (the repo is public)

- Never commit the real commute stops, addresses, workplace, Wi-Fi credentials,
  observation logs (`data/`), or `.env`. The real profile comes from env vars or the gitignored local file.
- Hosted deployments must set `SPARROW_ACCESS_TOKEN`.
- Committed examples use generic downtown stops (Lombard & 10th, Walnut & 10th).

## Needs owner approval

Spending money, buying hardware, new paid services (the Fly.io app is approved and live),
changing repo visibility (decided: stays public), publishing personal info,
destructive git operations. Hardware is dropped; don't restart it unless the owner asks.
