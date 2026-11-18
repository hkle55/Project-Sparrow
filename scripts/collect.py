#!/usr/bin/env python3
"""Run the prediction collector without the web server.

    .venv/bin/python scripts/collect.py              # every 30 s until Ctrl-C
    .venv/bin/python scripts/collect.py --once       # single poll (smoke test)

Writes to $SPARROW_DB or data/sparrow.sqlite (gitignored).
"""

import argparse
import asyncio
import logging
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.api.main import DEFAULT_DB  # noqa: E402
from app.config import load_config  # noqa: E402
from app.transit.client import TransitClient  # noqa: E402
from app.validation import store  # noqa: E402
from app.validation.collector import DEFAULT_INTERVAL_S, Collector  # noqa: E402


async def main(once: bool, interval: float) -> None:
    cfg = load_config()
    options = [o for m in cfg.modes.values() for o in m.options]
    db = store.connect(os.environ.get("SPARROW_DB") or DEFAULT_DB)
    routes, stops = {o.route for o in options}, {o.stop_id for o in options}
    client = TransitClient(routes, stops, cfg.settings.tz)
    collector = Collector(db, client, options, interval_s=interval)
    try:
        if once:
            await collector.tick()
            for table in ("polls", "predictions", "trip_stops", "vehicle_samples"):
                n = db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                print(f"{table}: {n}")
        else:
            await collector.run()
    finally:
        await client.aclose()
        db.close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--interval", type=float, default=DEFAULT_INTERVAL_S)
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    try:
        asyncio.run(main(args.once, args.interval))
    except KeyboardInterrupt:
        pass
