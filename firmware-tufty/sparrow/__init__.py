# Sparrow for the Pimoroni Tufty 2350 (Badgeware MicroPython). V1: work commute only.
#
# Polls /api/v1/device every 20 s, counts down locally every second, sleeps after 10 minutes
# without a button press (press any button to wake).
#   A = refresh   B = countdown / clock times   C = case light   UP/DOWN = screen brightness
#
# Badgeware provides these as built-ins: badge, screen, color, shape, font, rect, run,
# HIRES and BUTTON_*. All decisions live in core.py (unit-tested); this file only draws.
import os
import sys

os.chdir("/system/apps/sparrow")
sys.path.insert(0, "/system/apps/sparrow")

import secrets  # noqa: E402

import core  # noqa: E402
import wifi  # noqa: E402
from net import get_json  # noqa: E402

try:
    from badgeware import set_brightness
except ImportError:  # firmware without it: brightness buttons just do nothing
    def set_brightness(_value):
        pass

secrets.require("WIFI_SSID", "SPARROW_API_URL", "SPARROW_TOKEN")

badge.mode(HIRES)
W, H = 320, 240

POLL_MS = 20_000              # backend caches SEPTA for 20 s
AWAKE_MS = 10 * 60 * 1000     # sleep after 10 minutes idle

BLACK = color.rgb(0, 0, 0)
WHITE = color.rgb(255, 255, 255)
GREY = color.rgb(138, 138, 138)
RED = color.rgb(255, 74, 61)
YELLOW = color.rgb(255, 210, 63)
GREEN = color.rgb(61, 220, 106)
FONT = font.sins

model = None
fetched_ms = 0
last_ok_ms = None
last_poll_ms = None
last_poll_failed = False
last_error = ""
last_activity_ms = badge.ticks
clock_view = False
case_light = 0.0
brightness = 0.8
set_brightness(brightness)


# --- data ------------------------------------------------------------------------------

def poll():
    global model, fetched_ms, last_ok_ms, last_poll_ms, last_poll_failed, last_error
    last_poll_ms = badge.ticks
    try:
        payload = get_json(secrets.SPARROW_API_URL, {"X-Sparrow-Token": secrets.SPARROW_TOKEN})
        model = core.parse(payload)
        fetched_ms = last_ok_ms = badge.ticks
        last_poll_failed = False
        last_error = ""
    except Exception as e:  # network, TLS, HTTP or bad data: keep the last good model
        last_poll_failed = True
        last_error = str(e)[:38]


# --- drawing helpers -------------------------------------------------------------------

def fill(x, y, w, h, pen):
    screen.pen = pen
    screen.shape(shape.rectangle(x, y, w, h))


def outline(x, y, w, h, pen, width=2):
    screen.pen = pen
    screen.shape(shape.rectangle(x, y, w, h).stroke(width))


def text(s, x, y, size=1, pen=WHITE, align="left"):
    screen.font = FONT
    w, h = screen.measure_text(s, size)
    if align == "center":
        x -= w / 2
    elif align == "right":
        x -= w
    screen.pen = pen
    screen.text(s, rect(x, y, w + 2, h + 2), size)
    return w, h


def biggest(s, max_w, max_h, start=8):
    """Largest integer scale at which s fits in max_w x max_h (bitmap fonts scale by integers)."""
    screen.font = FONT
    for size in range(start, 0, -1):
        w, h = screen.measure_text(s, size)
        if w <= max_w and h <= max_h:
            return size
    return 1


def dashed(x, y, w, h, pen):
    for i in range(0, w, 13):
        fill(x + i, y, 8, 3, pen)
        fill(x + i, y + h - 3, 8, 3, pen)
    for j in range(0, h, 13):
        fill(x, y + j, 3, 8, pen)
        fill(x + w - 3, y + j, 3, 8, pen)


# --- screen sections (same layout as the CoreS3 / mockups) -------------------------------

def draw_top(now, no_conn):
    r = model.rec
    text("BUS " + r["route"] if r else "SPARROW", 6, 4, 2)
    if no_conn:
        label, pen = "NO WIFI", RED
    elif model.simulated:
        label, pen = "SIM", YELLOW
    else:
        chips = {"live": ("LIVE", GREEN), "stale": ("STALE", YELLOW)}
        label, pen = chips.get(model.status, ("SCHED", YELLOW))
    screen.font = FONT
    cw = screen.measure_text(label, 1)[0] + 12
    outline(W - cw - 4, 6, cw, 22, pen)
    text(label, W - cw / 2 - 4, 10, 1, pen, "center")
    x = W - cw - 12
    w, _ = text(core.et_time(now), x, 10, 1, GREY, "right")
    if not badge.usb_connected():
        pct = badge.battery_level()
        text("%d%%" % pct, x - w - 10, 10, 1, RED if pct <= 15 else GREY, "right")


def draw_scene(now):
    """The web app's 120x26 pixel bus, at 2x. Distance tracks the recommended bus."""
    s, ox, oy = 2, 40, 28

    def px(x, y, w, h, pen):
        fill(ox + x * s, oy + y * s, w * s, h * s, pen)

    px(0, 21, 120, 1, color.rgb(58, 58, 58))
    for x in range(2, 120, 8):
        px(x, 24, 4, 1, color.rgb(42, 42, 42))
    px(110, 7, 1, 14, GREY)
    px(106, 3, 9, 6, color.rgb(47, 128, 237))
    px(108, 5, 5, 2, WHITE)
    r = model.rec
    if not r:
        return
    until = max(0, r["bus_at"] - now)
    p = 0 if until >= 900 else 1 - until / 900
    bx, by = int(-4 + p * 84), 10
    dim = r["approx"]
    body = color.rgb(105, 105, 105) if dim else color.rgb(232, 232, 232)
    glass = color.rgb(34, 34, 34) if dim else color.rgb(51, 65, 79)
    stripe = color.rgb(100, 0, 0) if dim else color.rgb(208, 2, 27)

    def b(x, y, w, h, pen):
        px(bx + x, by + y, w, h, pen)

    b(1, 0, 22, 1, body)
    b(0, 1, 24, 9, body)
    for i in range(4):
        b(2 + i * 4, 2, 3, 3, glass)
    b(18, 2, 2, 7, glass)
    b(21, 2, 3, 4, color.rgb(127, 179, 224))
    b(0, 6, 18, 1, stripe)
    b(20, 6, 4, 1, stripe)
    b(23, 8, 1, 1, YELLOW)
    for wx in (3, 16):
        b(wx, 9, 5, 3, color.rgb(17, 17, 17))
        b(wx + 1, 10, 1, 1, GREY)


def draw_hero(now, no_conn):
    r = model.rec
    if not r:
        text("NO BUS", W / 2, 100, biggest("NO BUS", 280, 56), GREY, "center")
        text(model.msg, W / 2, 160, 1, WHITE, "center")
        return
    state, minutes, spare = core.hero(model, now)
    if state in (core.LEAVE, core.READY):
        ready = state == core.READY
        if clock_view:
            label = "GET READY - LEAVE AT" if ready else "LEAVE AT"
            big = core.et_time(r["leave_at"])
        else:
            label = "GET READY" if ready else "LEAVE IN"
            big = str(minutes)
        text(label, 12, 88, 1, YELLOW if ready else GREY)
        size = biggest(big, 200 if clock_view else 120, 62)
        w, _ = text(big, 10, 104, size)
        if not clock_view:
            text("min", 20 + w, 136, 2)
            text("by " + core.et_time(r["leave_at"]), W - 10, 150, 1, GREY, "right")
        if ready:
            outline(4, 84, int(w) + 120, 82, YELLOW, 3)
    elif state == core.NOW:
        fill(6, 86, W - 12, 78, WHITE)
        text("LEAVE NOW", W / 2, 100, biggest("LEAVE NOW", 290, 52), BLACK, "center")
    elif state == core.TIGHT:
        dashed(6, 86, W - 12, 78, RED)
        text("TIGHT - GO", W / 2, 94, biggest("TIGHT - GO", 280, 46), WHITE, "center")
        text("<1 min to spare" if spare < 60 else "%d min to spare" % core.floor_minutes(spare),
             W / 2, 146, 1, RED, "center")
    else:
        text("CHECKING...", W / 2, 116, 2, GREY, "center")
    if (r["approx"] or no_conn) and state in (core.LEAVE, core.READY):
        text("~ not live", W - 10, 88, 1, YELLOW, "right")

    if no_conn:
        line = "Offline: countdown may be off"
    elif r["alt"]:
        al = r["alt"]["leave_at"] - now
        line = ("Safer: %s - leave in %dm" % (r["alt"]["route"], core.floor_minutes(al))
                if al >= 0 else "Safer: bus " + r["alt"]["route"])
    else:
        line = r["why"]
    text(line, W / 2, 168, 1, RED if no_conn else GREY, "center")


def draw_rows(now):
    for i, row in enumerate(model.rows):
        y = 190 + i * 25
        text(row["route"], 8, y, 2)
        for j in range(core.MAX_ARRIVALS):
            x = 136 + j * 72
            if j >= len(row["t"]):
                text("-", x, y, 2, GREY, "right")
                continue
            at, kind = row["t"][j]
            live = kind == "l"
            to = at - now
            if clock_view:
                label, size = ("" if live else "~") + core.et_time(at, True), 1
            else:
                mins = "now" if to <= 30 else str(core.floor_minutes(to))
                label, size = ("" if live else "~") + mins, 2
            state = core.cell(model, row, at, now)
            pen = GREY if state == core.MISSED else (WHITE if live else YELLOW)
            w, h = text(label, x, y + (4 if clock_view else 0), size, pen, "right")
            if state == core.MISSED:
                fill(x - w, y + h // 2, w, 2, GREY)
            elif state == core.CELL_TIGHT:
                text("!", x + 2, y, size, RED)
        if not clock_view:
            text("min", W - 4, y + 6, 1, GREY, "right")


# --- main loop -------------------------------------------------------------------------

def handle_input(now_ms):
    global last_activity_ms, clock_view, case_light, brightness
    if badge.pressed():
        last_activity_ms = now_ms
    if badge.pressed(BUTTON_A):
        poll()
    if badge.pressed(BUTTON_B):
        clock_view = not clock_view
    if badge.pressed(BUTTON_C):
        case_light = 0.0 if case_light else 0.6
    if badge.pressed(BUTTON_UP):
        brightness = min(1.0, brightness + 0.1)
        set_brightness(brightness)
    if badge.pressed(BUTTON_DOWN):
        brightness = max(0.2, brightness - 0.1)
        set_brightness(brightness)


def update():
    now_ms = badge.ticks
    handle_input(now_ms)

    connected = wifi.connect()  # non-blocking; Badgeware shows its own error if it gives up
    if connected and (last_poll_ms is None or now_ms - last_poll_ms >= POLL_MS):
        poll()
    elif not connected and last_poll_ms is not None and now_ms - last_poll_ms >= POLL_MS:
        globals()["last_poll_failed"] = True
        globals()["last_error"] = "Wi-Fi not connected"

    fill(0, 0, W, H, BLACK)
    if model is None:
        msg = "NO CONNECTION" if last_poll_failed else "CONNECTING..."
        text(msg, W / 2, 96, 2, RED if last_poll_failed else WHITE, "center")
        if last_poll_failed:
            text(last_error, W / 2, 140, 1, GREY, "center")
    else:
        now = core.device_now(model, fetched_ms, now_ms)
        no_conn = core.no_connection(last_poll_failed, last_ok_ms, now_ms)
        draw_top(now, no_conn)
        draw_scene(now)
        draw_hero(now, no_conn)
        draw_rows(now)
        # The case glows on LEAVE NOW / TIGHT (no speaker on the Tufty), else the user's setting.
        urgent = core.hero(model, now)[0] in (core.NOW, core.TIGHT)
        badge.caselights(1.0 if urgent and (now_ms // 500) % 2 else case_light)

    if now_ms - last_activity_ms >= AWAKE_MS:
        badge.caselights(0)
        badge.sleep()  # any button wakes it; boot relaunches Sparrow


run(update)
