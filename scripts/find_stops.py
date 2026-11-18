#!/usr/bin/env python3
"""Look up GTFS stop IDs and directions for a route from SEPTA's static GTFS.

Downloads gtfs_public.zip into data/gtfs/ (gitignored) on first run.

    .venv/bin/python scripts/find_stops.py --route 40 --name "Lombard"
    .venv/bin/python scripts/find_stops.py --route 42 --direction 1 --name "Walnut St & 10th"
"""

import argparse
import csv
import io
import urllib.request
import zipfile
from pathlib import Path

GTFS_URL = "https://github.com/septadev/GTFS/releases/latest/download/gtfs_public.zip"
DATA = Path(__file__).resolve().parents[1] / "data" / "gtfs"


def bus_zip() -> zipfile.ZipFile:
    path = DATA / "gtfs_public.zip"
    if not path.exists():
        DATA.mkdir(parents=True, exist_ok=True)
        print(f"downloading {GTFS_URL} ...")
        urllib.request.urlretrieve(GTFS_URL, path)
    outer = zipfile.ZipFile(path)
    return zipfile.ZipFile(io.BytesIO(outer.read("google_bus.zip")))


def rows(z: zipfile.ZipFile, name: str):
    with z.open(name) as fh:
        yield from csv.DictReader(io.TextIOWrapper(fh, "utf-8-sig"))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--route", required=True)
    ap.add_argument("--direction", type=int, choices=[0, 1])
    ap.add_argument("--name", default="", help="case-insensitive substring of stop name")
    args = ap.parse_args()

    z = bus_zip()
    feed = next(rows(z, "feed_info.txt"))
    print(f"feed {feed['feed_version']} valid {feed['feed_start_date']}..{feed['feed_end_date']}")
    for d in rows(z, "directions.txt"):
        if d["route_id"] == args.route:
            dest = d["direction_destination"]
            print(f"direction {d['direction_id']}: {d['direction']} -> {dest}")
    stops = {r["stop_id"]: r for r in rows(z, "stops.txt")}
    for r in rows(z, "route_stops.txt"):
        if r["route_id"] != args.route:
            continue
        if args.direction is not None and int(r["direction_id"]) != args.direction:
            continue
        s = stops.get(r["stop_id"], {})
        if args.name.lower() in s.get("stop_name", "").lower():
            print(
                f"dir {r['direction_id']} #{int(r['route_stop_sort_order']):3d}  "
                f"stop_id {r['stop_id']:>6}  {s.get('stop_name')}  "
                f"({s.get('stop_lat')}, {s.get('stop_lon')})"
            )


if __name__ == "__main__":
    main()
