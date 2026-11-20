# Sparrow decision core for the Tufty 2350 (MicroPython). Plain Python with no badge
# imports, so it also runs under CPython for unit tests (firmware-tufty/tests).
#
# This is a port of firmware/src/core/sparrow_core.cpp, with the same rules and the same
# test vectors. It parses /api/v1/device and decides what the screen should say. If you
# change a rule here, change it in the C++ core and frontend/device.html too.

MAX_ROWS = 2
MAX_ARRIVALS = 3
LEAVE_NOW_S = 60      # under a minute of slack: LEAVE NOW
NO_CONN_AFTER_S = 45  # no successful poll for this long: NO WIFI

# Hero states
LEAVE, READY, NOW, TIGHT, CHECKING, NO_BUS = "leave", "ready", "now", "tight", "checking", "nobus"
# Cell states
OK, CELL_TIGHT, MISSED = "ok", "tight", "missed"


class Model:
    def __init__(self):
        self.server_now = 0
        self.status = "offline"  # live | stale | offline
        self.age_s = -1
        self.ready_s = 180
        self.simulated = False
        # rec: dict with route, action, leave_at, bus_at, walk_s, kind, approx, why, alt
        self.rec = None
        # rows: [{"route": "40", "walk_s": 240, "t": [(epoch, kind), ...]}]
        self.rows = []
        self.msg = ""


def parse(payload):
    """Build a Model from the decoded JSON payload. Raises ValueError on bad input."""
    if not isinstance(payload, dict) or payload.get("v") != 1:
        raise ValueError("unsupported payload")
    now = payload.get("now")
    if not isinstance(now, int):
        raise ValueError("missing now")
    m = Model()
    m.server_now = now
    st = payload.get("st", "offline")
    m.status = st if st in ("live", "stale") else "offline"
    m.age_s = payload.get("age", -1)
    m.ready_s = payload.get("rdy", 180)
    m.simulated = bool(payload.get("sim", False))
    m.msg = str(payload.get("msg", ""))[:63]

    rec = payload.get("rec")
    if rec is not None:
        if not rec.get("l") or not rec.get("b"):
            raise ValueError("recommendation without times")
        alt = rec.get("alt")
        m.rec = {
            "route": str(rec.get("r", ""))[:5],
            "action": str(rec.get("a", "")),
            "leave_at": int(rec["l"]),
            "bus_at": int(rec["b"]),
            "walk_s": int(rec.get("w", 0)),
            "kind": str(rec.get("k", "s"))[:1] or "s",
            "approx": bool(rec.get("x", True)),  # assume not-live unless told otherwise
            "why": str(rec.get("why", ""))[:48],
            "alt": None if not alt else {
                "route": str(alt.get("r", ""))[:5],
                "leave_at": int(alt.get("l", 0)),
                "bus_at": int(alt.get("b", 0)),
            },
        }

    for row in (payload.get("rows") or [])[:MAX_ROWS]:
        times = []
        for a in (row.get("t") or [])[:MAX_ARRIVALS]:
            times.append((int(a[0]), str(a[1])[:1] if len(a) > 1 else "s"))
        route = str(row.get("r", ""))[:5]
        m.rows.append({"route": route, "walk_s": int(row.get("w", 0)), "t": times})
    return m


def floor_minutes(seconds):
    """Whole minutes, rounded DOWN, never negative: a countdown must not overstate time left."""
    return 0 if seconds <= 0 else int(seconds // 60)


def hero(m, now):
    """Return (state, minutes, spare_s) for the big part of the screen."""
    r = m.rec
    if r is None:
        return (NO_BUS, 0, 0)
    left = r["leave_at"] - now
    until_bus = r["bus_at"] - now
    if r["action"] == "tight" or left < 0:
        # Server said TIGHT, or the leave time passed since the last poll.
        if until_bus >= r["walk_s"]:
            return (TIGHT, 0, until_bus - r["walk_s"])
        return (CHECKING, 0, 0)
    if left < LEAVE_NOW_S:
        return (NOW, 0, 0)
    if left < m.ready_s:
        return (READY, floor_minutes(left), 0)
    return (LEAVE, floor_minutes(left), 0)


def cell(m, row, at, now):
    """Catch state of one listed arrival right now. Buffer is implied by the recommendation."""
    r = m.rec
    buffer = (r["bus_at"] - r["leave_at"] - r["walk_s"]) if r else 120
    to_bus = at - now
    if to_bus < row["walk_s"]:
        return MISSED
    if to_bus < row["walk_s"] + buffer:
        return CELL_TIGHT
    return OK


def device_now(m, fetched_ms, now_ms):
    """No RTC sync needed: server time + whole seconds since that response arrived."""
    return m.server_now + (now_ms - fetched_ms) // 1000


def no_connection(last_poll_failed, last_ok_ms, now_ms):
    if not last_poll_failed:
        return False
    return last_ok_ms is None or (now_ms - last_ok_ms) // 1000 > NO_CONN_AFTER_S


# --- Eastern time without a timezone database ----------------------------------------
# US rule since 2007: EDT from the 2nd Sunday in March 02:00 EST (07:00 UTC)
# to the 1st Sunday in November 02:00 EDT (06:00 UTC).

def _days_from_civil(y, mo, d):
    # Howard Hinnant's algorithm: days since 1970-01-01.
    y -= mo <= 2
    era = (y if y >= 0 else y - 399) // 400
    yoe = y - era * 400
    doy = (153 * (mo + (-3 if mo > 2 else 9)) + 2) // 5 + d - 1
    doe = yoe * 365 + yoe // 4 - yoe // 100 + doy
    return era * 146097 + doe - 719468


def _civil_from_days(z):
    z += 719468
    era = (z if z >= 0 else z - 146096) // 146097
    doe = z - era * 146097
    yoe = (doe - doe // 1460 + doe // 36524 - doe // 146096) // 365
    y = yoe + era * 400
    doy = doe - (365 * yoe + yoe // 4 - yoe // 100)
    mp = (5 * doy + 2) // 153
    d = doy - (153 * mp + 2) // 5 + 1
    mo = mp + (3 if mp < 10 else -9)
    return (y + (mo <= 2), mo, d)


def _nth_sunday(y, mo, n):
    first = _days_from_civil(y, mo, 1)
    weekday = (first + 4) % 7  # 1970-01-01 was a Thursday (0 = Sunday)
    return first + (7 - weekday) % 7 + 7 * (n - 1)


def et_offset_s(epoch):
    y = _civil_from_days(epoch // 86400)[0]
    start = _nth_sunday(y, 3, 2) * 86400 + 7 * 3600
    end = _nth_sunday(y, 11, 1) * 86400 + 6 * 3600
    return -4 * 3600 if start <= epoch < end else -5 * 3600


def et_time(epoch, compact=False):
    """'7:41 PM' (or '7:41p' when compact) in Eastern time."""
    local = epoch + et_offset_s(epoch)
    secs = local % 86400
    h24, mins = secs // 3600, (secs % 3600) // 60
    h = h24 % 12 or 12
    if compact:
        return "%d:%02d%s" % (h, mins, "a" if h24 < 12 else "p")
    return "%d:%02d %s" % (h, mins, "AM" if h24 < 12 else "PM")
