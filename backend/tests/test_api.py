import json
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import httpx
import pytest
from fastapi.testclient import TestClient

from app.api import main as main_mod
from app.config import EXAMPLE_CONFIG, load_config
from app.simulation import SCENARIOS
from app.transit.client import TransitClient
from tests.feedbuilder import Stop, Trip, build_feed

NY = ZoneInfo("America/New_York")
NOW = datetime(2026, 11, 18, 22, 0, tzinfo=UTC)  # 5:00 pm ET
CFG = load_config(EXAMPLE_CONFIG)
S40, S42 = "22265", "14884"


def m(x):
    return NOW + timedelta(minutes=x)


def sched_payload(route, trips):
    rows = [
        {
            "Route": route,
            "trip_id": t,
            "Direction": "1",
            "DateCalender": at.astimezone(NY).strftime("%m/%d/%y %I:%M %p").lower(),
            "DirectionDesc": "Somewhere",
        }
        for t, at in trips
    ]
    return {route: rows}


class Upstream:
    """Fake SEPTA. Set `down = True` to simulate an outage."""

    def __init__(self, feed: bytes, schedules: dict):
        self.feed, self.schedules, self.down = feed, schedules, False

    def __call__(self, req: httpx.Request) -> httpx.Response:
        if self.down:
            raise httpx.ConnectError("unreachable", request=req)
        if req.url.path.endswith(".pb"):
            return httpx.Response(200, content=self.feed)
        key = (req.url.params["stop_id"], req.url.params["req2"])
        return httpx.Response(200, json=self.schedules.get(key, {}))


def app_for(tc, **kw):
    kw = {"db_path": ":memory:", "collect": False, "access_token": "", **kw}
    return main_mod.create_app(CFG, tc, **kw)


def make_client(upstream, monkeypatch, now=NOW):
    monkeypatch.setattr(main_mod, "now_utc", lambda: now)
    tc = TransitClient(
        {"40", "42"},
        {S40, S42},
        NY,
        http=httpx.AsyncClient(transport=httpx.MockTransport(upstream)),
        clock=lambda: now,
        attempts=1,
    )
    return TestClient(app_for(tc))


@pytest.fixture
def upstream():
    feed = build_feed(
        NOW - timedelta(seconds=25),
        [
            Trip("t40a", route="40", stops=[Stop(S40, m(11))]),
            Trip("t40b", route="40", vehicle=None, stops=[Stop(S40, m(25))]),
            Trip("t40x", route="40", direction_id=0, stops=[Stop("other", m(4))]),
            Trip("t42a", route="42", stops=[Stop(S42, m(14))]),
        ],
    )
    schedules = {
        (S40, "40"): sched_payload("40", [("t40a", m(10)), ("t40b", m(24)), ("t40c", m(38))]),
        (S42, "42"): sched_payload("42", [("t42a", m(13)), ("t42b", m(27))]),
    }
    return Upstream(feed, schedules)


def test_health(upstream, monkeypatch):
    with make_client(upstream, monkeypatch) as c:
        assert c.get("/health").json() == {"status": "ok"}


def test_work_commute_live(upstream, monkeypatch):
    with make_client(upstream, monkeypatch) as c:
        body = c.get("/api/v1/commute/work").json()
    assert body["configured"] and not body["simulated"]
    assert body["data"]["status"] == "live" and body["data"]["feed_age_s"] == 25
    rec = body["rec"]
    assert rec["route"] == "40" and rec["action"] == "leave_in"
    assert rec["leave_in_s"] == 300 and rec["kind"] == "live" and rec["approx"] is False
    r40 = body["routes"][0]
    assert r40["route"] == "40" and r40["preferred"]
    assert [(a["trip"], a["kind"]) for a in r40["arrivals"]] == [
        ("t40a", "live"),
        ("t40b", "estimated"),
        ("t40c", "scheduled"),
    ]
    assert [a["kind"] for a in body["routes"][1]["arrivals"]] == ["live", "scheduled"]


def test_response_is_compact(upstream, monkeypatch):
    with make_client(upstream, monkeypatch) as c:
        raw = c.get("/api/v1/commute/work").content
    assert len(raw) < 2048, len(raw)  # small enough for an ESP32 buffer
    assert "null" not in raw.decode()


def test_outage_keeps_last_good_then_goes_offline(upstream, monkeypatch):
    now = {"t": NOW}
    monkeypatch.setattr(main_mod, "now_utc", lambda: now["t"])
    tc = TransitClient(
        {"40", "42"}, {S40, S42}, NY,
        http=httpx.AsyncClient(transport=httpx.MockTransport(upstream)),
        clock=lambda: now["t"], attempts=1, monotonic=lambda: now["t"].timestamp(),
    )
    with TestClient(app_for(tc)) as c:
        assert c.get("/api/v1/commute/work").json()["data"]["status"] == "live"
        upstream.down = True
        now["t"] = NOW + timedelta(minutes=2)  # feed now 145 s old
        body = c.get("/api/v1/commute/work").json()
        assert body["data"]["status"] == "stale" and "ConnectError" in body["data"]["error"]
        assert body["rec"]["kind"] == "stale" and body["rec"]["approx"] is True
        now["t"] = NOW + timedelta(minutes=12)  # feed 745 s old -> discarded
        body = c.get("/api/v1/commute/work").json()
        assert body["data"]["status"] == "offline"
        kinds = {a["kind"] for r in body["routes"] for a in r["arrivals"]}
        assert kinds <= {"scheduled"}  # never presented as live


def test_home_unconfigured(upstream, monkeypatch):
    with make_client(upstream, monkeypatch) as c:
        body = c.get("/api/v1/commute/home").json()
    assert body["configured"] is False and "isn't set up" in body["message"]
    assert "rec" not in body and body["routes"] == []


def test_unknown_mode_and_scenario_404(upstream, monkeypatch):
    with make_client(upstream, monkeypatch) as c:
        assert c.get("/api/v1/commute/nowhere").status_code == 404
        assert c.get("/api/v1/commute/work?sim=nope").status_code == 404


@pytest.mark.parametrize("name", list(SCENARIOS))
def test_every_scenario_is_marked_simulated(upstream, monkeypatch, name):
    with make_client(upstream, monkeypatch) as c:
        body = c.get(f"/api/v1/commute/work?sim={name}").json()
    assert body["simulated"] is True and body["scenario"] == name


@pytest.mark.parametrize(
    "name, route, action",
    [
        ("normal", "40", "leave_in"),
        ("early_bus", "40", "get_ready"),
        ("missed_preferred", "42", "leave_in"),
        ("route_42", "42", "leave_in"),
        ("leave_now", "40", "leave_now"),
        ("tight", "40", "tight"),
    ],
)
def test_scenario_outcomes(upstream, monkeypatch, name, route, action):
    with make_client(upstream, monkeypatch) as c:
        rec = c.get(f"/api/v1/commute/work?sim={name}").json()["rec"]
    assert (rec["route"], rec["action"]) == (route, action)


def test_no_service_scenario_has_message(upstream, monkeypatch):
    with make_client(upstream, monkeypatch) as c:
        body = c.get("/api/v1/commute/work?sim=no_service").json()
    assert "rec" not in body and body["message"]


def test_scenarios_listed(upstream, monkeypatch):
    with make_client(upstream, monkeypatch) as c:
        ids = [s["id"] for s in c.get("/api/v1/scenarios").json()]
    assert ids == list(SCENARIOS)


def test_modes_listed(upstream, monkeypatch):
    with make_client(upstream, monkeypatch) as c:
        modes = c.get("/api/v1/modes").json()
    assert {x["mode"]: x["configured"] for x in modes} == {"work": True, "home": False}


def test_payload_json_roundtrip(upstream, monkeypatch):
    with make_client(upstream, monkeypatch) as c:
        json.loads(c.get("/api/v1/commute/work").content)


def test_tight_scenario_includes_safer_alternative(upstream, monkeypatch):
    with make_client(upstream, monkeypatch) as c:
        rec = c.get("/api/v1/commute/work?sim=tight").json()["rec"]
    assert rec["action"] == "tight" and rec["leave_in_s"] == 0
    assert rec["alt"]["route"] == "40" and rec["alt"]["action"] == "leave_in"  # 24m 40 beats 19m 42


# --- observations, report, access token ----------------------------------------------------


def test_observation_roundtrip(upstream, monkeypatch):
    with make_client(upstream, monkeypatch) as c:
        opts = c.get("/api/v1/observe/options").json()
        assert {(o["route"], o["stop_id"]) for o in opts} == {("40", S40), ("42", S42)}
        r = c.post("/api/v1/observations", json={"route": "40", "stop_id": S40,
                                                 "vehicle_id": " 3381 "})
        assert r.status_code == 201 and r.json()["arrived_at"] == NOW.timestamp()
        rows = c.get("/api/v1/observations").json()
        assert rows[0]["vehicle_id"] == "3381"
        assert c.delete(f"/api/v1/observations/{rows[0]['id']}").status_code == 204
        assert c.get("/api/v1/observations").json() == []
        assert c.delete("/api/v1/observations/999").status_code == 404


@pytest.mark.parametrize(
    "body",
    [
        {"route": "40", "stop_id": "nope"},
        {"route": "99", "stop_id": S40},
        {"route": "40", "stop_id": S40, "arrived_at": NOW.timestamp() - 2 * 86400},
        {"route": "40", "stop_id": S40, "arrived_at": NOW.timestamp() + 3600},
    ],
)
def test_observation_validation(upstream, monkeypatch, body):
    with make_client(upstream, monkeypatch) as c:
        assert c.post("/api/v1/observations", json=body).status_code == 422


def test_validation_report_endpoint(upstream, monkeypatch):
    with make_client(upstream, monkeypatch) as c:
        r = c.get("/api/v1/validation/report")
    assert r.status_code == 200 and "Not enough data yet" in r.text


def test_access_token(upstream, monkeypatch):
    monkeypatch.setattr(main_mod, "now_utc", lambda: NOW)
    tc = TransitClient({"40", "42"}, {S40, S42}, NY, clock=lambda: NOW, attempts=1,
                       http=httpx.AsyncClient(transport=httpx.MockTransport(upstream)))
    with TestClient(app_for(tc, access_token="s3cret")) as c:
        assert c.get("/health").status_code == 200
        assert c.get("/api/v1/commute/work").status_code == 401
        assert c.get("/").status_code == 401
        work = "/api/v1/commute/work"
        assert c.get(work, headers={"X-Sparrow-Token": "wrong"}).status_code == 401
        assert c.get(work, headers={"X-Sparrow-Token": "s3cret"}).status_code == 200
        r = c.get("/?key=s3cret")
        assert r.status_code == 200 and "sparrow_token" in r.headers["set-cookie"]
        assert c.get("/api/v1/commute/work").status_code == 200  # cookie now set


# --- device payload ------------------------------------------------------------------------


def test_device_payload_matches_web_and_is_small(upstream, monkeypatch):
    with make_client(upstream, monkeypatch) as c:
        web = c.get("/api/v1/commute/work").json()
        raw = c.get("/api/v1/device").content
    d = json.loads(raw)
    assert len(raw) < 700, len(raw)
    assert d["now"] == web["now"] and d["st"] == "live" and d["age"] == 25
    assert d["rec"] == {
        "r": "40", "a": "leave_in", "l": web["rec"]["leave_at"],
        "b": web["rec"]["arrives_at"], "w": 240, "k": "l", "x": False,
        "why": "Route 40 preferred",
    }
    assert [r["r"] for r in d["rows"]] == ["40", "42"]
    assert [k for _, k in d["rows"][0]["t"]] == ["l", "e", "s"]
    assert "sim" not in d and "msg" not in d
    # buffer is recoverable on the device: b - l - w == 120 s
    assert d["rec"]["b"] - d["rec"]["l"] - d["rec"]["w"] == 120


def test_device_tight_carries_alternative(upstream, monkeypatch):
    with make_client(upstream, monkeypatch) as c:
        d = c.get("/api/v1/device?sim=tight").json()
    assert d["sim"] is True and d["rec"]["a"] == "tight"
    assert set(d["rec"]["alt"]) == {"r", "l", "b"}


def test_device_no_service_has_message(upstream, monkeypatch):
    with make_client(upstream, monkeypatch) as c:
        d = c.get("/api/v1/device?sim=no_service").json()
    assert "rec" not in d and d["msg"]


def test_device_stale_and_offline_kinds(upstream, monkeypatch):
    with make_client(upstream, monkeypatch) as c:
        stale = c.get("/api/v1/device?sim=stale").json()
        off = c.get("/api/v1/device?sim=offline").json()
    assert stale["st"] == "stale" and stale["rec"]["k"] == "o" and stale["rec"]["x"] is True
    assert off["st"] == "offline" and {k for r in off["rows"] for _, k in r["t"]} == {"s"}


def test_device_unknown_mode_404(upstream, monkeypatch):
    with make_client(upstream, monkeypatch) as c:
        assert c.get("/api/v1/device?mode=nowhere").status_code == 404
