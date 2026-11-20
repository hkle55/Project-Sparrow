# Sparrow firmware (V1: work commute only)

Targets (pick one with `-e`):
- **`m5cores3`**: M5Stack CoreS3 (ESP32-S3, 2.0" 320×240 touch, 500 mAh). Pixel-font layout with
  the pixel bus; tap the arrival rows to switch countdown/clock times, tap elsewhere to refresh.
- **`m5sticks3`**: M5Stack StickS3 (ESP32-S3, 1.14" 240×135, 250 mAh). Button A/B = refresh.

See `docs/hardware.md`.
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
- `src/ui/`: one layout per screen size (`ui_240x135.cpp`, `ui_320x240.cpp`); each build
  compiles exactly one. Layouts only draw. They use the generic LovyanGFX sprite API.
- `src/main.cpp`: M5Stack hardware (M5Unified display, buttons/touch, power, speaker; Wi-Fi;
  HTTPS).
- `include/secrets.example.h`: copy to `include/secrets.h` (gitignored) and add the Wi-Fi
  password, backend URL, and token.

## Build and flash

```bash
pip install platformio
cd firmware
cp include/secrets.example.h include/secrets.h   # then edit it
pio test -e native             # core logic tests, no hardware needed
pio run -e m5cores3            # compile (or -e m5sticks3)
pio run -e m5cores3 -t upload  # flash over USB-C
pio device monitor             # serial log
```

To try it before the backend is hosted, point `SPARROW_API_URL` at a laptop on the same
Wi-Fi (`http://<laptop-ip>:8000/api/v1/device`, with uvicorn started with `--host 0.0.0.0`)
or add `?sim=normal` for demo data.

## Measured so far

- Compiles for the StickS3 (RAM 15.5%, flash 35.9%) and CoreS3 (RAM 15.5%, flash 17.8%).
- Native core tests: 12/12.
- Not yet measured (needs hardware): battery life, wake-to-data time, readability.
