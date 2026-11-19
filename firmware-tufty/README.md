# Sparrow for the Pimoroni Tufty 2350 (V1: work commute only)

A Badgeware MicroPython app for the [Tufty 2350](https://shop.pimoroni.com/products/tufty-2350)
(RP2350, 2.8" 320×240 IPS, 1000 mAh, 5 buttons). It has the same screen layout as the CoreS3
firmware in `firmware/`. **Not run on real hardware yet.**

## Buttons

| Button | Does |
|---|---|
| A | Refresh now |
| B | Switch countdown ⇄ Eastern clock times |
| C | Case light on/off |
| UP / DOWN | Screen brightness |
| Any | Wakes it from sleep (it sleeps after 10 min idle) |

The case also flashes on LEAVE NOW / TIGHT. The Tufty has no speaker.

## Files

- `sparrow/__init__.py`: the app (drawing, buttons, polling, sleep). Uses Badgeware built-ins.
- `sparrow/core.py`: decision logic, a port of `firmware/src/core` with the same test cases.
  Plain Python, unit-tested on a normal computer.
- `sparrow/net.py`: HTTPS GET that **verifies** the server certificate (Pimoroni's bundled
  helper doesn't) and sends the `X-Sparrow-Token` header.
- `sparrow/roots.py`: Let's Encrypt root certificates (same as the M5 firmware).
- `sparrow/icon.png`: 24×24 pixel bus for the Badgeware menu.
- `main.py`: optional boot file that opens Sparrow on power-up instead of the app menu.
- `secrets.example.py`: template for `/secrets.py` on the badge. Never commit the real one.

## Install (once the badge arrives)

1. Put the badge in disk mode: **tap RESET twice**. It mounts as a USB drive.
2. Copy `secrets.example.py` to the drive as **`secrets.py`** and fill in her Wi-Fi, the
   backend URL and the token. (Badgeware already has a `secrets.py` there; edit it and add
   the two `SPARROW_` lines.)
3. Copy the `sparrow/` folder into the drive's **`apps/`** folder (so it's `apps/sparrow/`).
4. Optional, for a gift that just works: rename the drive's `main.py` to `main.py.orig` and copy
   ours in. It then boots straight into Sparrow.
5. Eject and tap RESET once.

To try it before the backend is hosted, set `SPARROW_API_URL` to
`http://<laptop-ip>:8000/api/v1/device?sim=normal` with the laptop server started with
`--host 0.0.0.0`.

## Development checks (no hardware needed)

```bash
.venv/bin/python -m pytest firmware-tufty/tests   # logic + HTTPS helper tests
.venv/bin/ruff check firmware-tufty
pip install mpy-cross && mpy-cross firmware-tufty/sparrow/__init__.py   # MicroPython syntax
```

## Known unknowns until it's on real hardware

- Font sizes and positions. The layout measures text at runtime, but `font.sins` glyph
  metrics are untested.
- Certificate checking: assumes this MicroPython build's `tls.SSLContext` accepts two
  `load_verify_locations` calls (one per root). If the HTTPS check fails on-device, that's
  the first thing to look at.
- Battery life, Wi-Fi reconnect after sleep, and how fast it wakes.
