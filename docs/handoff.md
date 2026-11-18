# Handoff

_Last updated: 2026-11-18. V1 = physical Sparrow for the work commute only._

## Status

- M0–M3: done. Web prototype on live SEPTA data.
- TIGHT CONNECTION state: done.
- M4 prediction validation: tooling done. Real collection starts when the backend is hosted.
- M5 deployment: prepared (Fly.io, ~$2–3/mo). **Waiting on the owner's spend approval and
  account creation.**
- **V1 scope (2026-11-18):** work commute only (40 @ Lombard & 21st, 42 @ Walnut & 21st).
  No mode toggle on the device. The return commute is out of scope and not a blocker. Home
  Wi-Fi only.
- Device API: `GET /api/v1/device` (~330 B), with a `/device` pixel preview.
- M6 hardware: recommendation is the **M5Stack StickS3** ($21.50). See docs/hardware.md.
  **Nothing purchased.**
- M7 firmware: `firmware/` (PlatformIO). The core is native-tested (12/12), and it compiles for
  the StickS3. Not run on real hardware.

## Uncommitted work (if present)

On 2026-11-18, git commit/push was blocked by the session's permission classifier. If
`git status` shows uncommitted files on `feat/v1-device-api`, they're the device API,
the preview, the V1 scope docs, the hardware doc, and the firmware. Commit them in the
logical groups listed in the session report.

## Environment

- Cloud environment `project-sparrow`: the setup script creates `.venv`, and `SPARROW_CONFIG_JSON`
  holds the real profile (verified from a fresh session).
- PlatformIO isn't in the setup script yet. Use `pip install platformio` in a scratch venv.
- Validation DB `data/sparrow.sqlite` is container-local. Real collection belongs on the host.

## Tests

- Backend: `cd backend && ../.venv/bin/pytest -q`: 149 passed. `ruff check . ../scripts`: clean.
- Firmware: `cd firmware && pio test -e native`: 12 passed. `pio run -e m5sticks3`: builds.
- CI jobs: backend, docker, firmware (firmware job added in this round, not yet run on GitHub).

## Owner decisions pending

1. Approve hosting spend (Fly.io ~$2–3/mo) and create the account (docs/deployment.md).
2. Approve buying hardware: 1–2× M5Stack StickS3 ($21.50 each) + USB-C cable.

## Next steps

1. Deploy, set the token, and send her the `/observe` link to start collecting validation data.
2. When the StickS3 arrives: flash it, measure battery life and wake-to-data time, and test
   readability on her actual walk.
3. After 2+ weeks of data: tune `safety_buffer_min` from the validation report.
