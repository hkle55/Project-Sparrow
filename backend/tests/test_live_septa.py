"""Live integration tests against SEPTA. Run explicitly: `pytest -m live`."""

import asyncio
from datetime import UTC, datetime, timedelta

import pytest

from app.config import EXAMPLE_CONFIG, load_config
from app.predictions.arrivals import build_arrivals
from app.transit.client import TransitClient

pytestmark = pytest.mark.live


def test_live_feeds_return_sane_data():
    cfg = load_config(EXAMPLE_CONFIG)
    mode = cfg.modes["work"]

    async def go():
        c = TransitClient(
            {o.route for o in mode.options}, {o.stop_id for o in mode.options}, cfg.settings.tz
        )
        try:
            tu = await c.trip_updates()
            scheds = [await c.schedule(o.stop_id, o.route) for o in mode.options]
            return tu, scheds
        finally:
            await c.aclose()

    tu, scheds = asyncio.run(go())
    assert tu.error is None, tu.error
    now = datetime.now(UTC)
    age = (now - tu.value.feed_timestamp).total_seconds()
    assert -60 < age < 300, f"feed age {age}s"
    for opt, sched in zip(mode.options, scheds, strict=True):
        assert sched.error is None, sched.error
        arrivals = build_arrivals(opt, now, tu.value, sched.value, cfg.settings)
        for a in arrivals:
            assert a.route == opt.route
            assert a.at >= now - timedelta(minutes=1)
