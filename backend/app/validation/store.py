"""SQLite storage for prediction validation. All times are UTC epoch seconds (REAL).

Tables
- polls: one row per collection attempt (feed freshness, errors)
- predictions: a row whenever SEPTA's predicted arrival for (trip, stop) changes
- trip_stops: first/last time each (trip, stop) was listed in trip updates
- vehicle_samples: GPS vehicle positions for trips on the watched routes (deduped)
- observations: manual, independently observed arrivals (ground truth)

The database lives under data/ (gitignored). It's private runtime data and never committed.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS polls (
    id INTEGER PRIMARY KEY,
    observed_at REAL NOT NULL,
    tu_feed_ts REAL,
    vp_feed_ts REAL,
    tu_error TEXT,
    vp_error TEXT
);
CREATE INDEX IF NOT EXISTS polls_time ON polls(observed_at);

CREATE TABLE IF NOT EXISTS predictions (
    id INTEGER PRIMARY KEY,
    observed_at REAL NOT NULL,
    feed_ts REAL NOT NULL,
    trip_ts REAL,
    route TEXT NOT NULL,
    stop_id TEXT NOT NULL,
    trip_id TEXT NOT NULL,
    service_date TEXT NOT NULL,
    vehicle_id TEXT,
    stop_sequence INTEGER,
    predicted_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS predictions_trip ON predictions(trip_id, service_date, stop_id);

CREATE TABLE IF NOT EXISTS trip_stops (
    trip_id TEXT NOT NULL,
    service_date TEXT NOT NULL,
    stop_id TEXT NOT NULL,
    route TEXT NOT NULL,
    stop_sequence INTEGER,
    vehicle_id TEXT,
    first_listed REAL NOT NULL,
    last_listed REAL NOT NULL,
    dropped_at REAL,          -- first poll where the trip was present but this stop wasn't
    PRIMARY KEY (trip_id, service_date, stop_id)
);

CREATE TABLE IF NOT EXISTS vehicle_samples (
    trip_id TEXT NOT NULL,
    service_date TEXT NOT NULL,
    vehicle_id TEXT NOT NULL,
    route TEXT NOT NULL,
    reported_at REAL NOT NULL,   -- vehicle's own GPS timestamp
    observed_at REAL NOT NULL,   -- when Sparrow saw it
    stop_sequence INTEGER,
    stop_id TEXT,
    status TEXT,
    lat REAL,
    lon REAL,
    PRIMARY KEY (trip_id, service_date, reported_at)
);

CREATE TABLE IF NOT EXISTS observations (
    id INTEGER PRIMARY KEY,
    recorded_at REAL NOT NULL,   -- when the observation was entered
    arrived_at REAL NOT NULL,    -- when the observer saw the bus arrive at the stop
    route TEXT NOT NULL,
    stop_id TEXT NOT NULL,
    vehicle_id TEXT,             -- fleet number painted on the bus, if noted
    note TEXT,
    source TEXT NOT NULL DEFAULT 'manual'
);
"""


def connect(path: str | Path) -> sqlite3.Connection:
    path = Path(path)
    if str(path) != ":memory:":
        path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript(SCHEMA)
    return conn


def add_observation(
    conn: sqlite3.Connection,
    *,
    recorded_at: float,
    arrived_at: float,
    route: str,
    stop_id: str,
    vehicle_id: str | None = None,
    note: str | None = None,
) -> int:
    cur = conn.execute(
        "INSERT INTO observations (recorded_at, arrived_at, route, stop_id, vehicle_id, note)"
        " VALUES (?, ?, ?, ?, ?, ?)",
        (recorded_at, arrived_at, route, stop_id, vehicle_id or None, note or None),
    )
    conn.commit()
    return cur.lastrowid
