# Sparrow

A pocket-sized, real-time SEPTA bus companion. At a glance it answers:

1. Which bus should I take?
2. When is it arriving?
3. When do I need to leave?

It was built for one daily Philadelphia commute, where buses running *early* kept
causing missed buses. Sparrow takes SEPTA's live stop-level predictions, subtracts
walking time and a safety buffer, and says **LEAVE IN 5m** so you don't have to do the
math. It's explicit whenever the data isn't live.

## Status

**Complete.** A hosted web app on real SEPTA data, used daily from a phone home-screen
shortcut. A physical ESP32 device was designed and its firmware written, but it was dropped
because the web app turned out to be enough. See [docs/handoff.md](docs/handoff.md).

What works today:
- Next 3 arrivals per route at the configured stops (Route 40 and Route 42 for work)
- Live / estimated / scheduled / stale labels, never mixed up
- Departure countdown (walk + 2 min buffer), with GET READY / LEAVE NOW states
- Route 40 preference, with Route 42 when it boards more than 5 min sooner
- Handles passed, canceled, and detoured buses, stale feeds, SEPTA outages, and lost connection
- Work and home commutes. Auto mode picks one by time of day; Switch mode overrides it
- TIGHT CONNECTION state when a bus is reachable only by cutting into the buffer and no
  safe bus comes soon after
- Simulation mode with labeled scenarios
- Prediction validation: collector, `/observe` page for manual arrival taps, accuracy report
  ([docs/validation.md](docs/validation.md))

## Architecture

```
SEPTA GTFS-RT trip updates ─┐
SEPTA BusSchedules (JSON) ──┴─> TransitClient (cache, retries, last-good)
                                   │
                         build_arrivals (merge + label)
                                   │
                         recommend (pure engine)
                                   │
                    FastAPI /api/v1/commute/{mode}
                         /               \
              web app             ESP32 (shelved)
```

Details: [docs/architecture.md](docs/architecture.md). Data source findings:
[docs/transit-research.md](docs/transit-research.md).

## Run it locally

**Easiest (macOS):** double-click **`Start Sparrow.command`** in the project folder in Finder.
The first time, it sets everything up (about a minute). After that it starts in a few
seconds and opens http://127.0.0.1:8000 in your browser. Close the Terminal window it opens
to stop Sparrow. It needs Python 3.12+ (macOS's built-in Python is too old) and links you
to the installer if it can't find one. If macOS refuses to open it, right-click it, choose
Open, then confirm.

**Manual setup:**

Requires Python 3.12+.

```bash
python3 -m venv .venv
.venv/bin/pip install -r backend/requirements-dev.txt
```

Optional: add your real stops to a private profile (gitignored):

```bash
cp config/commute.example.toml config/commute.local.toml
```

Start the server, then open http://127.0.0.1:8000:

```bash
cd backend && ../.venv/bin/uvicorn app.api.main:app --port 8000
```

Terminal view without the server:

```bash
.venv/bin/python scripts/next_arrivals.py work
```

## Tests

```bash
cd backend && ../.venv/bin/pytest -q          # offline unit tests (CI runs these)
cd backend && ../.venv/bin/pytest -m live -q  # hits the real SEPTA feeds
cd backend && ../.venv/bin/ruff check .
```

## Configuration

`config/commute.example.toml` documents every option. Sparrow loads `$SPARROW_CONFIG`,
otherwise `config/commute.local.toml` if it exists, otherwise the example. Key settings:
`safety_buffer_min` (2), `preference_threshold_min` (5), each route's `walk_min`, and the
staleness limits (`stale_after_s` 120, `discard_after_s` 600). Find stop IDs with
`scripts/find_stops.py --route 40 --direction 1 --name "Lombard"`.

The repository is public, so real commute stops belong only in the gitignored local
profile.

## API

`GET /api/v1/commute/work` returns about 1.3 KB of JSON with epoch-second times
(`now`, `rec.leave_at`, `routes[].arrivals[].at`). Clients count down locally and
correct for clock skew using `now`. Add `?sim=<scenario>` for demo data; the response is
then flagged `"simulated": true`. Also: `/api/v1/modes`, `/api/v1/scenarios`, `/health`.

## Known limitations

- Prediction accuracy isn't measured yet. The collector has run since 2026-11-20; the
  2-min buffer stays a guess until the validation report has a few weeks of data.
- Live predictions only cover trips that already have a bus assigned (roughly the next
  30 min). Later buses are scheduled times.
- BusSchedules times are minute-resolution.
- Route choice compares boarding times, not door-to-door time.
- Hosted on one Fly.io machine with one volume, so a host failure means downtime until
  Fly recovers it ([docs/deployment.md](docs/deployment.md)).

## Roadmap

Done: M0–M5 (engine, web app, validation tooling, hosting with auto-deploy). Optional:
tune the safety buffer from the validation report. Dropped: M6–M8 (hardware).
