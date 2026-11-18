#!/usr/bin/env python3
"""Record a manual bus arrival observation from the terminal.

    .venv/bin/python scripts/observe.py 40                 # Route 40 arrived just now
    .venv/bin/python scripts/observe.py 42 --ago 60 --bus 3399
    .venv/bin/python scripts/observe.py 40 --at "17:42:30" # local time today

The stop comes from the commute profile (first option for that route unless --stop).
Prefer the /observe web page on a phone. This is for entering notes after the fact.
"""

import argparse
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.api.main import DEFAULT_DB  # noqa: E402
from app.config import load_config  # noqa: E402
from app.validation import store  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("route")
ap.add_argument("--stop", help="stop_id (default: first configured stop for the route)")
ap.add_argument("--ago", type=float, default=0, help="seconds ago")
ap.add_argument("--at", help="local time HH:MM[:SS] today")
ap.add_argument("--bus", help="vehicle number")
ap.add_argument("--note")
args = ap.parse_args()

cfg = load_config()
opts = [o for m in cfg.modes.values() for o in m.options if o.route == args.route]
if args.stop:
    opts = [o for o in opts if o.stop_id == args.stop]
if not opts:
    sys.exit(f"route {args.route} / stop {args.stop} not in the commute profile")
now = datetime.now(UTC)
if args.at:
    parts = [int(x) for x in args.at.split(":")] + [0]
    local = now.astimezone(cfg.settings.tz).replace(hour=parts[0], minute=parts[1],
                                                   second=parts[2], microsecond=0)
    arrived = local.timestamp()
else:
    arrived = now.timestamp() - args.ago
db = store.connect(os.environ.get("SPARROW_DB") or DEFAULT_DB)
oid = store.add_observation(db, recorded_at=now.timestamp(), arrived_at=arrived,
                            route=args.route, stop_id=opts[0].stop_id, vehicle_id=args.bus,
                            note=args.note)
print(f"saved observation #{oid}: route {args.route} at {opts[0].stop_name}, "
      f"{datetime.fromtimestamp(arrived, UTC).astimezone(cfg.settings.tz):%H:%M:%S}")
