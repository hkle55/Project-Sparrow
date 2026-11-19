# Handoff

_Last updated: 2026-11-19. V1 = a physical Sparrow for the work commute only._

## Phases

| Phase | What | Status |
|---|---|---|
| 1. Software prototype | Live SEPTA data, recommendation engine (walk + 2-min buffer, 40 preferred, TIGHT), web app, device preview, `/observe` | **Done** |
| 2. Validation tooling | Collector, GPS-inferred and manual arrivals, accuracy report | **Done** (no real data yet) |
| 3. Hosting | Dockerfile, fly.toml, access token, deploy workflow | **Prepared. Waiting on owner approval (~$2–3/mo Fly.io) and account** |
| 4. Real-world web trial | Both phones use the hosted link for 1–2 weeks; she taps `/observe` ~30 times; collector runs 24/7 | Blocked on phase 3 |
| 5. Tune | Read the validation report; adjust `safety_buffer_min` if P95 early error says so | Blocked on phase 4 |
| 6. Hardware | M5Stack StickS3 recommended ($21.50). Firmware written, native-tested, compiles | **Waiting on purchase approval** |
| 7. Device bring-up | Flash, measure battery life and wake-to-data time, check readability on her walk | Blocked on phase 6 |
| 8. Daily use | She carries it. Iterate on feedback (vibration, screen size, enclosure) | Later |

## Running locally

Double-click `Start Sparrow.command` (macOS) or see README. It needs Python 3.12+.

## Environment

- Cloud environment `project-sparrow`: the setup script creates `.venv`, and `SPARROW_CONFIG_JSON`
  holds the real profile (verified from a fresh session).
- PlatformIO isn't in the setup script. `pip install platformio` in a scratch venv for
  firmware work.

## Tests

- Backend: `cd backend && ../.venv/bin/pytest -q` (149 passed). `ruff check . ../scripts`: clean.
- Firmware: `cd firmware && pio test -e native` (12 passed). `pio run -e m5sticks3` builds.
- CI: backend, docker, firmware jobs.

## Owner decisions pending

1. Hosting: approve Fly.io (~$2–3/mo) or Railway (~$5/mo), create the account.
2. Hardware: approve 1–2× StickS3 + USB-C cable, now or after the web trial.
