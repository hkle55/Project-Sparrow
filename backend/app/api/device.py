"""Compact payload for the physical Sparrow (ESP32). V1 is work-commute only.

It's derived from the same CommuteOut the web app gets, so the device and the web
simulator can never disagree. Short keys keep it around 400 bytes.

    {
      "v": 1,
      "now": 1795041111,          # server time (epoch s); the device counts down from this
      "st": "live",               # live | stale | offline (SEPTA data status)
      "age": 28,                  # seconds since SEPTA generated the data (omitted if none)
      "rdy": 180,                 # GET READY threshold (s); LEAVE NOW is < 60 s
      "sim": true,                # only present for simulated data
      "rec": {                    # omitted when nothing is catchable
        "r": "40",                # route
        "a": "leave_in",          # leave_in | get_ready | leave_now | tight
        "l": 1795041400,          # leave at (epoch s)
        "b": 1795041760,          # bus arrives at stop (epoch s)
        "w": 240,                 # walk time (s), to tell tight from missed locally
        "k": "l",                 # kind: l=live e=estimated s=scheduled o=old/stale
        "x": false,               # approximate (not a fresh live prediction)
        "why": "Route 40 preferred",
        "alt": {"r": "42", "l": 1795041900, "b": 1795042320}   # safer bus when a == tight
      },
      "rows": [                   # one per route, preferred first, up to 3 arrivals each
        {"r": "40", "w": 240, "t": [[1795041760, "l"], [1795042600, "s"]]}
      ],
      "msg": "No bus catchable with the current buffer"   # only when there's no rec
    }

Per-arrival catch state isn't sent: it changes every second, so the device recomputes it
from `t`, `w` and the safety buffer implied by `l` (buffer = b - l - w).
"""

from __future__ import annotations

from pydantic import BaseModel

from app.api.schemas import CommuteOut

KIND = {"live": "l", "estimated": "e", "scheduled": "s", "stale": "o"}


class DeviceAlt(BaseModel):
    r: str
    l: int  # noqa: E741 - wire format key
    b: int


class DeviceRec(BaseModel):
    r: str
    a: str
    l: int  # noqa: E741
    b: int
    w: int
    k: str
    x: bool
    why: str
    alt: DeviceAlt | None = None


class DeviceRow(BaseModel):
    r: str
    w: int
    t: list[tuple[int, str]]


class DeviceOut(BaseModel):
    v: int = 1
    now: int
    st: str
    age: int | None = None
    rdy: int = 180
    sim: bool | None = None
    rec: DeviceRec | None = None
    rows: list[DeviceRow] = []
    msg: str | None = None


def to_device(c: CommuteOut) -> DeviceOut:
    walk = {r.route: round(r.walk_min * 60) for r in c.routes}
    rows = sorted(c.routes, key=lambda r: not r.preferred)  # preferred route first
    rec = None
    if c.rec is not None:
        rec = DeviceRec(
            r=c.rec.route, a=c.rec.action, l=c.rec.leave_at, b=c.rec.arrives_at,
            w=walk.get(c.rec.route, 0), k=KIND[c.rec.kind], x=c.rec.approx,
            why=c.rec.reason[:48],
            alt=DeviceAlt(r=c.rec.alt.route, l=c.rec.alt.leave_at, b=c.rec.alt.arrives_at)
            if c.rec.alt else None,
        )
    return DeviceOut(
        now=c.now,
        st=c.data.status,
        age=c.data.feed_age_s,
        rdy=c.rec.ready_s if c.rec else 180,
        sim=True if c.simulated else None,
        rec=rec,
        rows=[
            DeviceRow(r=r.route, w=walk[r.route], t=[(a.at, KIND[a.kind]) for a in r.arrivals])
            for r in rows
        ],
        msg=c.message if c.rec is None else None,
    )
