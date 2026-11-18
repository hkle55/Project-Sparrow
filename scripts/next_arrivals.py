#!/usr/bin/env python3
"""Print the next arrivals for each route in a commute mode, straight from SEPTA.

Usage (from repo root):  .venv/bin/python scripts/next_arrivals.py [work|home]
"""

import asyncio
import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.config import load_config  # noqa: E402
from app.predictions.arrivals import build_arrivals  # noqa: E402
from app.transit.client import TransitClient  # noqa: E402


async def main(mode_key: str) -> int:
    cfg = load_config()
    mode = cfg.modes.get(mode_key)
    if mode is None:
        print(f"unknown mode {mode_key!r}; choose from {sorted(cfg.modes)}")
        return 2
    print(f"config: {cfg.source}")
    if not mode.configured:
        print(f"{mode.label}: not configured yet (no route options in the profile).")
        return 0

    tz = cfg.settings.tz
    client = TransitClient(
        {o.route for o in mode.options}, {o.stop_id for o in mode.options}, tz
    )
    try:
        tu = await client.trip_updates()
        now = datetime.now(UTC)
        if tu.error:
            print(f"!! trip updates unavailable: {tu.error}")
        else:
            age = (now - tu.value.feed_timestamp).total_seconds()
            print(f"trip updates generated {age:.0f}s ago")
        for opt in mode.options:
            sched = await client.schedule(opt.stop_id, opt.route)
            if sched.error:
                print(f"!! schedule unavailable for {opt.route}: {sched.error}")
            arrivals = build_arrivals(opt, now, tu.value, sched.value, cfg.settings)
            n = cfg.settings.arrivals_per_route
            print(
                f"\nRoute {opt.route} (dir {opt.direction_id}) "
                f"at {opt.stop_name} [{opt.stop_id}]"
            )
            if not arrivals:
                print("  no upcoming arrivals available")
            for a in arrivals[:n]:
                mins = (a.at - now).total_seconds() / 60
                local = a.at.astimezone(tz).strftime("%I:%M:%S %p")
                sched_s = ""
                if a.scheduled:
                    sched_s = f" sched {a.scheduled.astimezone(tz).strftime('%I:%M %p')}"
                print(
                    f"  {mins:5.1f} min  {local}  {a.kind.value.upper():9s} "
                    f"trip {a.trip_id} veh {a.vehicle_id or '-'}{sched_s}  {a.headsign or ''}"
                )
            if len(arrivals) < n:
                print(f"  (only {len(arrivals)} available; not padding with made-up buses)")
    finally:
        await client.aclose()
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main(sys.argv[1] if len(sys.argv) > 1 else "work")))
