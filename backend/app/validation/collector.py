"""Record SEPTA predictions and vehicle positions for the watched stops.

`record()` is pure-ish: it takes already-fetched snapshots plus `now` and writes rows, so
it's fully testable. `Collector.run()` is the async loop used by the app and CLI.
"""

from __future__ import annotations

import asyncio
import logging
import sqlite3
from collections.abc import Callable
from datetime import UTC, datetime

from app.config import RouteOption
from app.transit.client import TransitClient
from app.transit.models import TripUpdatesSnapshot, VehicleSnapshot

log = logging.getLogger(__name__)

DEFAULT_INTERVAL_S = 30.0  # SEPTA regenerates its feeds about every 30 s


def _ts(dt: datetime | None) -> float | None:
    return dt.timestamp() if dt else None


def record(
    conn: sqlite3.Connection,
    options: list[RouteOption],
    now: datetime,
    tu: TripUpdatesSnapshot | None,
    vp: VehicleSnapshot | None,
    tu_error: str | None = None,
    vp_error: str | None = None,
) -> None:
    t = now.timestamp()
    conn.execute(
        "INSERT INTO polls (observed_at, tu_feed_ts, vp_feed_ts, tu_error, vp_error)"
        " VALUES (?, ?, ?, ?, ?)",
        (t, _ts(tu.feed_timestamp if tu else None), _ts(vp.feed_timestamp if vp else None),
         tu_error, vp_error),
    )

    watched = {(o.route, o.direction_id): o for o in options}
    if tu is not None and tu_error is None:
        for opt in options:
            for p in tu.for_stop(opt.stop_id):
                if p.route != opt.route or p.direction_id not in (None, opt.direction_id):
                    continue
                date = p.start_date or ""
                last = conn.execute(
                    "SELECT predicted_at FROM predictions WHERE trip_id=? AND service_date=?"
                    " AND stop_id=? ORDER BY observed_at DESC LIMIT 1",
                    (p.trip_id, date, p.stop_id),
                ).fetchone()
                predicted = p.arrival.timestamp()
                if last is None or last["predicted_at"] != predicted:
                    conn.execute(
                        "INSERT INTO predictions (observed_at, feed_ts, trip_ts, route, stop_id,"
                        " trip_id, service_date, vehicle_id, stop_sequence, predicted_at)"
                        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        (t, tu.feed_timestamp.timestamp(), _ts(p.trip_timestamp), p.route,
                         p.stop_id, p.trip_id, date, p.vehicle_id, p.stop_sequence, predicted),
                    )
                conn.execute(
                    "INSERT INTO trip_stops (trip_id, service_date, stop_id, route, stop_sequence,"
                    " vehicle_id, first_listed, last_listed) VALUES (?, ?, ?, ?, ?, ?, ?, ?)"
                    " ON CONFLICT(trip_id, service_date, stop_id) DO UPDATE SET"
                    " last_listed=excluded.last_listed,"
                    " vehicle_id=COALESCE(excluded.vehicle_id, vehicle_id),"
                    " stop_sequence=COALESCE(excluded.stop_sequence, stop_sequence)",
                    (p.trip_id, date, p.stop_id, p.route, p.stop_sequence, p.vehicle_id, t, t),
                )
        # A trip still in the feed that no longer lists a stop it used to: it has gone by.
        for row in conn.execute(
            "SELECT trip_id, service_date, stop_id FROM trip_stops"
            " WHERE dropped_at IS NULL AND last_listed > ?",
            (t - 3 * 3600,),
        ).fetchall():
            trip = tu.trips.get(row["trip_id"])
            if trip is None or (trip.start_date or "") != row["service_date"]:
                continue
            if row["stop_id"] not in trip.remaining_stop_ids:
                conn.execute(
                    "UPDATE trip_stops SET dropped_at=? WHERE trip_id=? AND service_date=?"
                    " AND stop_id=?",
                    (t, row["trip_id"], row["service_date"], row["stop_id"]),
                )

    if vp is not None and vp_error is None:
        tracked = {
            (r["trip_id"], r["service_date"])
            for r in conn.execute(
                "SELECT DISTINCT trip_id, service_date FROM trip_stops WHERE last_listed > ?",
                (t - 3 * 3600,),
            )
        }
        for v in vp.vehicles:
            key = (v.trip_id, v.start_date or "")
            if key not in tracked and (v.route, v.direction_id) not in watched:
                continue
            conn.execute(
                "INSERT OR IGNORE INTO vehicle_samples (trip_id, service_date, vehicle_id, route,"
                " reported_at, observed_at, stop_sequence, stop_id, status, lat, lon)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (v.trip_id, v.start_date or "", v.vehicle_id, v.route, v.timestamp.timestamp(),
                 t, v.stop_sequence, v.stop_id, v.status, v.lat, v.lon),
            )
    conn.commit()


class Collector:
    def __init__(
        self,
        conn: sqlite3.Connection,
        client: TransitClient,
        options: list[RouteOption],
        interval_s: float = DEFAULT_INTERVAL_S,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self.conn, self.client, self.options = conn, client, options
        self.interval_s, self.clock = interval_s, clock
        self.polls = 0

    async def tick(self) -> None:
        tu = await self.client.trip_updates()
        vp = await self.client.vehicle_positions()
        # Only record a feed as "fresh data" if this tick actually fetched it without error.
        record(self.conn, self.options, self.clock(), tu.value, vp.value, tu.error, vp.error)
        self.polls += 1

    async def run(self) -> None:
        log.info("collector started: %d route options, every %.0fs", len(self.options),
                 self.interval_s)
        while True:
            try:
                await self.tick()
            except Exception:  # never let one bad tick kill the loop
                log.exception("collector tick failed")
            await asyncio.sleep(self.interval_s)
