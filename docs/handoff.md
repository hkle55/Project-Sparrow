# Handoff

_Last updated: 2026-11-23. **Project complete.** The web app is the final product; the
physical device was dropped at the user's request._

## Final state

| Phase | What | Status |
|---|---|---|
| 1. Software prototype | Live SEPTA data, recommendation engine (walk + 2-min buffer, 40 preferred, TIGHT), web app, `/observe` | **Done** |
| 2. Validation tooling | Collector, GPS-inferred and manual arrivals, accuracy report | **Done** |
| 3. Hosting | Fly.io app `sparrow-k7q2` (always on, ~$2–3/mo), access token, auto-deploy from `main` | **Live** |
| 4. Data collection | Collector runs 24/7 on the host | **Running** since 2026-11-20 |
| 5. Tune | Read the validation report; adjust `safety_buffer_min` if P95 early error says so | Optional, once a few weeks of data exist |
| 6–8. Hardware | Device selection, firmware, bring-up | **Dropped** (2026-11-23): she prefers the web app |

Extras shipped late: auto mode (work before 2 PM ET, home after; `settings.home_after`),
the home commute, and seasonal weather in the pixel bus scene.

## How it runs

- **Live site:** `https://sparrow-k7q2.fly.dev/`. Every route except `/health` needs the access
  token (owner's password manager). She uses it from a home-screen shortcut on her phone.
- **Deploys:** merge to `main` → CI → the Deploy workflow ships it to Fly. A failing CI run
  blocks the deploy.
- **Private config:** lives only in the Fly secret `SPARROW_CONFIG_TOML` (and the owner's
  gitignored `config/commute.local.toml`). Change it with
  `fly secrets set SPARROW_CONFIG_TOML="$(cat config/commute.local.toml)"`; the app restarts.
- **Shutting it down for good:** `fly apps destroy sparrow-k7q2`. Stopping alone still bills
  the volume.

## Hardware, for the record

Firmware was written for two candidates and never flashed. The branches are kept, unmerged:

- `feat/firmware-cores3`: M5Stack CoreS3 (C++, PlatformIO, M5Unified). Closed PR #14.
- `feat/firmware-tufty`: Pimoroni Tufty 2350 (MicroPython). Closed PR #15.

`firmware/` on `main` (the earlier StickS3 build) and `/api/v1/device` + `/device` stay, since
they're tested and harmless. Hardware research is in `docs/hardware.md`.

## Running locally

Double-click `Start Sparrow.command` (macOS) or see README. It needs Python 3.12+.

## Tests

- Backend: `cd backend && ../.venv/bin/pytest -q`. `ruff check . ../scripts`: clean.
- Firmware: `cd firmware && pio test -e native`.
- CI: backend, docker, firmware jobs.
