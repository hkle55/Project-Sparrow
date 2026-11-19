"""CPython tests for the Tufty decision core. Same vectors as firmware/test/test_core."""

import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "sparrow"))

import core  # noqa: E402

LIVE = json.loads(
    '{"v":1,"now":1000,"st":"live","age":15,"rdy":180,'
    '"rec":{"r":"40","a":"leave_in","l":1300,"b":1660,"w":240,"k":"l","x":false,'
    '"why":"Route 40 preferred"},'
    '"rows":[{"r":"40","w":240,"t":[[1100,"l"],[1660,"l"],[2500,"s"]]},'
    '{"r":"42","w":420,"t":[[1540,"s"],[1900,"l"]]}]}'
)


def test_parse_live_payload():
    m = core.parse(LIVE)
    assert m.server_now == 1000 and m.status == "live" and m.age_s == 15
    assert m.rec["route"] == "40" and m.rec["approx"] is False
    assert len(m.rows) == 2 and len(m.rows[0]["t"]) == 3 and len(m.rows[1]["t"]) == 2
    assert m.rows[0]["t"][2][1] == "s"


@pytest.mark.parametrize(
    "bad",
    [None, [], {"v": 2, "now": 1}, {"v": 1}, {"v": 1, "now": 5, "rec": {"r": "40"}}],
)
def test_parse_rejects_bad_payloads(bad):
    with pytest.raises(ValueError):
        core.parse(bad)


def test_missing_approx_defaults_to_not_live():
    d = json.loads(json.dumps(LIVE))  # deep copy
    del d["rec"]["x"]
    assert core.parse(d).rec["approx"] is True


def test_no_rec_has_message():
    m = core.parse({"v": 1, "now": 1, "st": "live", "rows": [], "msg": "No bus catchable"})
    assert m.rec is None and m.msg == "No bus catchable"
    assert core.hero(m, 1)[0] == core.NO_BUS


def test_truncates_rows_and_arrivals():
    d = {"v": 1, "now": 1, "st": "live", "rows": [
        {"r": "1", "w": 1, "t": [[1, "l"], [2, "l"], [3, "l"], [4, "l"]]},
        {"r": "2", "w": 1, "t": []}, {"r": "3", "w": 1, "t": []}]}
    m = core.parse(d)
    assert len(m.rows) == core.MAX_ROWS and len(m.rows[0]["t"]) == core.MAX_ARRIVALS


def test_countdown_floors():
    m = core.parse(LIVE)
    assert core.hero(m, 1000) == (core.LEAVE, 5, 0)
    assert core.hero(m, 1001)[1] == 4  # 4:59 left shows 4, never 5


def test_states_over_time():
    m = core.parse(LIVE)  # leave 1300, bus 1660, walk 240, ready 180
    assert core.hero(m, 1120)[0] == core.LEAVE
    assert core.hero(m, 1121) == (core.READY, 2, 0)
    assert core.hero(m, 1241)[0] == core.NOW
    assert core.hero(m, 1300)[0] == core.NOW
    assert core.hero(m, 1350) == (core.TIGHT, 0, 70)
    assert core.hero(m, 1421)[0] == core.CHECKING


def test_server_tight_with_alternative():
    d = {"v": 1, "now": 1000, "st": "live", "rows": [], "rec": {
        "r": "40", "a": "tight", "l": 900, "b": 1300, "w": 240, "k": "l", "x": False,
        "why": "Tight", "alt": {"r": "42", "l": 1500, "b": 1900}}}
    m = core.parse(d)
    assert core.hero(m, 1000) == (core.TIGHT, 0, 60)
    assert m.rec["alt"]["route"] == "42"


def test_cells():
    m = core.parse(LIVE)  # buffer = 1660 - 1300 - 240 = 120
    row = m.rows[0]
    assert core.cell(m, row, 1000 + 239, 1000) == core.MISSED
    assert core.cell(m, row, 1000 + 240, 1000) == core.CELL_TIGHT
    assert core.cell(m, row, 1000 + 359, 1000) == core.CELL_TIGHT
    assert core.cell(m, row, 1000 + 360, 1000) == core.OK


def test_floor_minutes():
    assert [core.floor_minutes(s) for s in (-30, 59, 60, 599)] == [0, 0, 1, 9]


def test_device_clock_and_connection():
    m = core.parse(LIVE)
    assert core.device_now(m, 5000, 5999) == 1000
    assert core.device_now(m, 5000, 6000) == 1001
    assert not core.no_connection(False, 1000, 999999)
    assert not core.no_connection(True, 1000, 1000 + 45000)
    assert core.no_connection(True, 1000, 1000 + 46000)
    assert core.no_connection(True, None, 10)


NY = ZoneInfo("America/New_York")


@pytest.mark.parametrize("epoch", [
    # around the 2026 and 2027 DST switches, midnight, and noon
    *range(1772953200 - 7200, 1772953200 + 7200, 900),   # 2026-03-08 spring forward
    *range(1793512800 - 7200, 1793512800 + 7200, 900),   # 2026-11-01 fall back
    *range(1804406400, 1804406400 + 86400, 3600),         # a day in March 2027
    1795041111, 1795050000, 0, 1700000000,
])
def test_et_time_matches_zoneinfo(epoch):
    dt = datetime.fromtimestamp(epoch, UTC).astimezone(NY)
    expected = dt.strftime("%-I:%M %p")
    assert core.et_time(epoch) == expected
    assert core.et_time(epoch, compact=True) == expected[:-3] + expected[-2].lower()
