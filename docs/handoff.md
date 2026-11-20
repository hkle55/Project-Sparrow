# Handoff

_Last updated: 2026-11-19 (night). V1 = a physical Sparrow for the work commute only._

## Phases

| Phase | What | Status |
|---|---|---|
| 1. Software prototype | Live SEPTA data, recommendation engine (walk + 2-min buffer, 40 preferred, TIGHT), web app, device preview, `/observe` | **Done** |
| 2. Validation tooling | Collector, GPS-inferred and manual arrivals, accuracy report | **Done** (no real data yet) |
| 3. Hosting | Fly.io app `sparrow-k7q2` (always on, ~$2–3/mo), access token, deploy workflow | **Live** (auto-deploy pending GitHub secret) |
| 4. Data collection | Collector runs 24/7 on the host (GPS-inferred arrivals; no taps from her, since it's a surprise) | **Running** since 2026-11-20 |
| 5. Tune | Read the validation report; adjust `safety_buffer_min` if P95 early error says so | Blocked on phase 4 |
| 6. Hardware | CoreS3 vs Tufty 2350. Both firmware versions written (draft PRs #14, #15) | **Owner picks next session** |
| 7. Device bring-up | Flash, measure battery life and wake-to-data time, check readability on her walk | Blocked on phase 6 |
| 8. Daily use | She carries it. Iterate on feedback (vibration, screen size, enclosure) | Later |

## Open decision: which device (decide next session)

Sparrow is a **Christmas gift**, so she must not know. No trial with her, and no `/observe` taps
from her. Validation relies on the hosted collector's GPS-inferred arrivals (and any testing by
the owner).

Two firmware versions exist as **draft PRs**. Merge the one the owner picks; keep the other branch.

| | M5Stack CoreS3 | Pimoroni Tufty 2350 |
|---|---|---|
| PR / branch | #14 `feat/firmware-cores3` | #15 `feat/firmware-tufty` |
| Screen | 2.0" 320x240, touch | 2.8" 320x240, 5 buttons |
| Size / battery | 54x54x15.5 mm / 500 mAh | 84x76x20 mm / 1000 mAh |
| Price / stock (2026-11-19) | $59.90, in stock | ~$56, appears in stock (UK) |
| Code | `firmware/` PlatformIO env `m5cores3` (C++, M5Unified) | `firmware-tufty/` Badgeware MicroPython app |
| Risk | Low (same library as the existing firmware) | Higher (new chip/API, written from Pimoroni examples) |

Both use the same 320x240 layout (mockups were shown to the owner). Neither has run on hardware.
Rejected: StickS3 (screen too small for the owner), PaperS3 (EOL, no light), PaperMono (out of
stock), T5 S3 Pro Lite (sold out, $71), TICKEY (Kickstarter, ships too late).

Deadline: about 5 weeks to Christmas. Order the device this week (shipping 1-2 weeks), and
**hosting must be live**, because the device can't work without the server.

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

1. Device: CoreS3 or Tufty 2350 (then order it this week).
2. Auto-deploy: add the `FLY_API_TOKEN` secret and `DEPLOY_ENABLED=true` variable in GitHub.
3. Optional: allow `apt install libsdl2-dev` in the cloud workspace, to render the real CoreS3
   firmware drawing to screenshots before the device arrives.
