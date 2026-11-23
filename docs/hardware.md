# Hardware selection (Milestone 6)

> **Dropped (2026-11-23).** She prefers the web app, so no device was bought. Kept for the
> record; see docs/handoff.md for the firmware branches.

**Status: recommendation ready. Nothing purchased.** Buying anything needs owner approval.

## What V1 needs

- Pocketable, rechargeable over USB-C, with an enclosure out of the box (no soldering or 3D
  printing for the first prototype).
- Wi-Fi to her home network only (V1 scope). The device calls `GET /api/v1/device` on the
  hosted backend.
- A screen that fits: route, a big countdown, and 2 rows × 3 arrival times. The 240×135
  layout in `frontend/device.html` proves this fits.
- At least one physical button (wake/refresh). No mode toggle (V1 scope).
- Battery for a morning routine: wake, glance repeatedly for ~15–30 min, sleep.
- Mainstream Arduino/PlatformIO support, so the firmware stays simple.

## Candidates (specs checked 2026-11-18)

| Board | MCU | Screen | Battery | Enclosure | Buttons / alerts | Size, weight | Price | Notes |
|---|---|---|---|---|---|---|---|---|
| **M5Stack StickS3** (K150) | ESP32-S3 (PICO-1, 8 MB flash, 8 MB PSRAM) | 1.14" color IPS, 240×135, ST7789P3 | **250 mAh built in** | **Yes**, magnetic back | Programmable buttons + power button; speaker (ES8311 codec, 1 W amp); IMU; IR | **48×24×15 mm, 20 g** | **$21.50** (M5Stack store, in stock) | Successor to the EOL StickC Plus2. Released Jan 2026. Power-off draw 14 µA. |
| LilyGO T-Display-S3 | ESP32-S3 (16 MB / 8 MB) | 1.9" color, 320×170, ST7789 | None. JST 1.25 mm LiPo port with charging (~500 mA) | No (acrylic plate). Needs a printed case | 2 programmable buttons + reset | Bare board | ~$15–25 | Bigger, nicer screen, but needs a battery and case sourced separately |
| M5Stack CoreInk (K048) | ESP32-PICO-D4 (older, no PSRAM) | 1.54" e-ink, 200×200, B/W | 390 mAh built in | Yes | Dial switch (up/press/down), button, buzzer, RTC wake | 56×40×16 mm, 31.5 g | ~$40–60 (retailers vary) | Readable in sun, zero power to hold the image. Slow refresh (~1 s full), no color urgency |
| M5StickC Plus2 | ESP32-PICO-V3 | 1.14" 240×135 | 200 mAh | Yes | 3 buttons, buzzer | — | — | **End of life**, don't buy |
| M5Stack PaperS3 | ESP32-S3 | 4.7" e-ink 960×540 | 1800 mAh | Yes | Touch | Too big for a pocket | ~$50–60 | Too big |

Sources: [M5Stack StickS3 store page](https://shop.m5stack.com/products/m5sticks3-esp32s3-mini-iot-dev-kit),
[CNX Software on StickS3](https://www.cnx-software.com/2026/01/23/m5stack-sticks3-esp32-s3-mini-iot-dev-kit-features-1-14-inch-color-display-speaker-and-mic-for-voice-interaction/),
[LilyGO T-Display-S3 wiki](https://wiki.lilygo.cc/products/t-display-series/t-display-s3/),
[M5Stack CoreInk docs](https://docs.m5stack.com/en/core/CoreInk),
[StickC Plus2 EOL listing](https://shop.m5stack.com/products/m5stickc-plus2-esp32-mini-iot-development-kit),
[PaperS3 docs](https://docs.m5stack.com/en/core/PaperS3). Prices are store snapshots. Confirm
at checkout.

## Recommendation: M5Stack StickS3, $21.50

Why:
- **Zero assembly:** battery, case, USB-C charging, and buttons all included. It works the
  day it arrives.
- **Truly pocketable:** 48×24×15 mm and 20 g, about the size of a car key fob.
- **The screen fits the layout:** 240×135 is exactly what `/device` previews. The countdown
  digit is ~52 px tall, readable at arm's length.
- **ESP32-S3** with PSRAM gives plenty of headroom for TLS, JSON, and a frame buffer.
- **Cheap and current:** $21.50 and in stock. The Plus2 is EOL; this is its successor.

Trade-offs to know:
- **Battery is small (250 mAh).** Rough estimate (to be measured in M8): Wi-Fi plus a lit
  screen draws ~100–150 mA, so ~1.5–2.5 h of screen-on time. A morning routine of ~20 min
  screen-on, then power-off (14 µA), means **charging every few days**. Overnight
  charging on her nightstand is the simplest habit.
- **No vibration motor.** The speaker can beep (e.g. at LEAVE NOW). Vibration would need
  an add-on and is a V2 idea.
- **1.14" is small.** If it proves too small in real use, step up to the T-Display-S3
  (1.9") with a LiPo and case. The firmware's core logic is board-independent, so only
  the display layer changes.
- **E-ink alternative (CoreInk):** better sunlight readability and battery life, but no
  color for urgency, slower updates, an older chip, and twice the price. Revisit if
  battery life disappoints.

## Bill of materials (V1 prototype)

| Item | Qty | Est. cost | Notes |
|---|---|---|---|
| M5Stack StickS3 (SKU K150) | 1 (2 recommended) | $21.50 each | A second unit keeps a dev board while she uses the first |
| USB-C cable (data-capable) | 1 | $0–8 | For flashing. Any phone charger works for charging |
| Shipping | | ~$5–15 | Varies |
| **Total** | | **≈ $27–60** | One unit + cable at minimum, two units recommended |

No soldering, no 3D printing, no extra battery.

## Open questions for real-world testing (M8)

- Measured battery life with a 20 s poll and the screen on.
- Is 1.14" readable while walking? Is the beep useful or annoying?
- Wake latency: power on → Wi-Fi → first data. Target < 5 s.
