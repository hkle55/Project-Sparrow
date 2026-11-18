import asyncio
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import httpx

from app.transit import client as client_mod
from app.transit.client import TransitClient
from tests.feedbuilder import Stop, Trip, build_feed

T0 = datetime(2026, 11, 18, 22, 0, tzinfo=UTC)
FEED = build_feed(T0, [Trip("a", stops=[Stop("S", T0 + timedelta(minutes=5))])])


class Clock:
    def __init__(self):
        self.now = T0
        self.mono = 1000.0

    def advance(self, seconds):
        self.now += timedelta(seconds=seconds)
        self.mono += seconds


def make(handler, clock):
    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return TransitClient(
        {"40"},
        {"S"},
        ZoneInfo("America/New_York"),
        http=http,
        clock=lambda: clock.now,
        monotonic=lambda: clock.mono,
    )


def run(coro):
    return asyncio.run(coro)


def no_sleep(monkeypatch):
    async def instant(_):
        return None

    monkeypatch.setattr(client_mod.asyncio, "sleep", instant)


def test_caches_within_ttl(monkeypatch):
    calls = []

    def handler(req):
        calls.append(req.url)
        return httpx.Response(200, content=FEED)

    clock = Clock()
    c = make(handler, clock)

    async def go():
        a = await c.trip_updates()
        clock.advance(10)
        b = await c.trip_updates()
        clock.advance(15)  # now 25 s > 20 s TTL
        await c.trip_updates()
        return a, b

    a, b = run(go())
    assert a.error is None and a.value.for_stop("S")
    assert b.value is a.value
    assert len(calls) == 2


def test_retries_5xx_then_succeeds(monkeypatch):
    no_sleep(monkeypatch)
    responses = iter([httpx.Response(503), httpx.Response(200, content=FEED)])
    c = make(lambda req: next(responses), Clock())
    got = run(c.trip_updates())
    assert got.error is None and got.value is not None


def test_timeout_keeps_last_good_data_and_reports_error(monkeypatch):
    no_sleep(monkeypatch)
    state = {"fail": False}

    def handler(req):
        if state["fail"]:
            raise httpx.ConnectTimeout("timed out", request=req)
        return httpx.Response(200, content=FEED)

    clock = Clock()
    c = make(handler, clock)

    async def go():
        good = await c.trip_updates()
        state["fail"] = True
        clock.advance(30)
        bad = await c.trip_updates()
        return good, bad

    good, bad = run(go())
    assert bad.value is good.value  # last good snapshot still available
    assert bad.fetched_at == good.fetched_at  # caller can see how old it is
    assert "ConnectTimeout" in bad.error


def test_garbage_response_is_an_error_not_a_crash(monkeypatch):
    no_sleep(monkeypatch)
    c = make(lambda req: httpx.Response(200, content=b"<html>oops</html>"), Clock())
    got = run(c.trip_updates())
    assert got.value is None and got.error


def test_backs_off_after_failure(monkeypatch):
    no_sleep(monkeypatch)
    calls = []

    def handler(req):
        calls.append(1)
        return httpx.Response(500)

    clock = Clock()
    c = make(handler, clock)

    async def go():
        await c.trip_updates()  # 2 attempts
        clock.advance(3)
        await c.trip_updates()  # within back-off: no request
        clock.advance(10)
        await c.trip_updates()  # 2 more attempts

    run(go())
    assert len(calls) == 4


def test_4xx_not_retried(monkeypatch):
    no_sleep(monkeypatch)
    calls = []

    def handler(req):
        calls.append(1)
        return httpx.Response(404)

    got = run(make(handler, Clock()).trip_updates())
    assert got.error and len(calls) == 1


def test_schedule_fetch_parses_json():
    payload = {
        "40": [
            {"Route": "40", "trip_id": "t1", "Direction": "1", "DateCalender": "11/18/26 05:24 pm"}
        ]
    }

    def handler(req):
        assert req.url.params["stop_id"] == "S" and req.url.params["req2"] == "40"
        return httpx.Response(200, json=payload)

    got = run(make(handler, Clock()).schedule("S", "40"))
    assert got.error is None and got.value[0].trip_id == "t1"


def test_schedule_invalid_json_is_error():
    got = run(make(lambda r: httpx.Response(200, content=b"not json"), Clock()).schedule("S", "40"))
    assert got.value is None and "invalid JSON" in got.error
