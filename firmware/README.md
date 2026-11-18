# Sparrow firmware (V1: work commute only)

Target: **M5Stack StickS3** (ESP32-S3, 1.14" 240×135, 250 mAh). See `docs/hardware.md`.
Not flashed on real hardware yet, because nothing has been purchased.

## What it does

- Joins her home Wi-Fi (an optional second network, e.g. a phone hotspot, can be added).
- Every 20 s, calls `GET /api/v1/device` on the hosted backend with the `X-Sparrow-Token`
  header, over HTTPS verified against Let's Encrypt roots (`include/root_ca.h`).
- Counts down locally every second from the server's clock (no NTP needed).
- Shows: route, LEAVE IN / GET READY / LEAVE NOW / TIGHT · GO, the safer alternative, and
  3 arrivals for routes 40 and 42. Non-live times get `~`, tight ones `!`, missed ones are
  struck through. Status chip: LIVE / STALE / SCHED / SIM / NO WIFI. Battery %.
- Beeps once on LEAVE NOW or TIGHT.
- **Buttons:** power button press = on, double press = off. Button A or B = refresh now
  and keep the screen awake. Powers itself off after 10 min without a press.
- No work/home toggle (V1 scope).

## Layout

- `src/core/`: board-independent parsing and decisions, unit-tested natively. Mirrors
  `frontend/device.html`, the browser preview of this exact screen.
- `src/main.cpp`: StickS3 hardware (M5Unified display, buttons, power, speaker; Wi-Fi;
  HTTPS).
- `include/secrets.example.h`: copy to `include/secrets.h` (gitignored) and add the Wi-Fi
  password, backend URL, and token.

## Build and flash

```bash
pip install platformio
cd firmware
cp include/secrets.example.h include/secrets.h   # then edit it
pio test -e native             # core logic tests, no hardware needed
pio run -e m5sticks3           # compile
pio run -e m5sticks3 -t upload # flash over USB-C
pio device monitor             # serial log
```

To try it before the backend is hosted, point `SPARROW_API_URL` at a laptop on the same
Wi-Fi (`http://<laptop-ip>:8000/api/v1/device`, with uvicorn started with `--host 0.0.0.0`)
or add `?sim=normal` for demo data.

## Measured so far

- Compiles for the StickS3: RAM 15.5% (50.9 KB), flash 35.9% (1.2 MB).
- Native core tests: 12/12.
- Not yet measured (needs hardware): battery life, wake-to-data time, readability.
