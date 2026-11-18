# SEPTA Transit Data Research

Findings from live requests made 2026-11-18 (weekday, ~5:20 pm ET). Everything
below was observed in real responses unless marked **unverified**.

## Summary

| Need | Source | Verdict |
|---|---|---|
| Stop-level live arrival predictions | GTFS-RT **Trip Updates** | **Primary source.** Absolute predicted arrival time per upcoming stop, per trip, with vehicle ID. |
| Scheduled arrivals (fallback, longer horizon) | `BusSchedules` JSON API | **Secondary source.** Today's scheduled times at a stop; same `trip_id`s as GTFS-RT. Minute resolution. |
| Vehicle GPS | GTFS-RT **Vehicle Positions**, `TransitView` JSON | Available; not needed for v1 (trip updates already give per-stop times). Useful for validation later. |
| Alerts / detours | GTFS-RT **Service Alerts**, `Alerts/get_alert_data.php` | Available. Detoured stops also appear as `SKIPPED` in trip updates. |
| Static schedule / stop IDs | GTFS static (`septadev/GTFS` GitHub releases) | Used offline to verify stop IDs and directions. Not loaded at runtime. |

## Endpoints (all verified 200 OK, no API key)

| Feed | URL | Format |
|---|---|---|
| Trip updates | `https://www3.septa.org/gtfsrt/septa-pa-us/Trip/rtTripUpdates.pb` | GTFS-RT 2.0 protobuf, ~1.27 MB, ~3,600 entities (all bus/trolley/metro routes) |
| Vehicle positions | `https://www3.septa.org/gtfsrt/septa-pa-us/Vehicle/rtVehiclePosition.pb` | GTFS-RT protobuf, ~95 KB, ~1,100 vehicles |
| Service alerts | `https://www3.septa.org/gtfsrt/septa-pa-us/Service/rtServiceAlerts.pb` | GTFS-RT protobuf, ~400 alerts |
| Scheduled stop times | `https://www3.septa.org/api/BusSchedules/index.php?stop_id=<id>&req2=<route>&req6=<count>` | JSON |
| Vehicles on a route | `https://www3.septa.org/api/TransitView/index.php?route=<route>` | JSON |
| Stops on a route | `https://www3.septa.org/api/Stops/index.php?req1=<route>` | JSON (both directions mixed, no direction field) |
| Route alerts | `https://www3.septa.org/api/Alerts/get_alert_data.php?req1=bus_route_<route>` | JSON (returned HTTP **501** with a valid body; don't rely on status code) |
| Static GTFS | `https://github.com/septadev/GTFS/releases/latest/download/gtfs_public.zip` (also `www3.septa.org/developer/gtfs_public.zip`) | zip containing `google_bus.zip` |

Not working: `www3.septa.org/gtfs_realtime/bus/realtime/...` (404), `www3.septa.org/api/` index (403).
Older `api.goswift.ly` feed URLs are listed as replaced by the Mobility Database; not used.

## Trip Updates: what's actually in them

- `header.timestamp` = when SEPTA generated the feed. The file is regenerated roughly
  **every 30 s** (Last-Modified and header timestamp advanced on ~30 s boundaries during a
  3-minute sample). Header age at fetch time was 15–40 s.
- Each entity: `trip.trip_id`, `route_id`, `direction_id`, `start_date`, `start_time`,
  `vehicle.id`, `timestamp`, and a list of `stop_time_update`s.
- `stop_time_update` has `stop_id`, `stop_sequence`, `arrival.time` (absolute POSIX
  seconds). `delay` and `uncertainty` are **not populated** (always 0/unset).
- Only **upcoming** stops are listed. Once a bus passes a stop, that stop disappears from the
  trip's list. This is the cleanest "already passed" signal available.
- `stop_time_update.schedule_relationship = SKIPPED` (1) is used heavily for detours
  (e.g. 132 skipped stop-updates on Route 42 eastbound during an active detour).
- `trip.schedule_relationship = CANCELED` (3) appears (33 trips at sample time).
- ~2,400 of ~3,600 entities have **no vehicle assigned**. Trips heading to the boarding
  stops in the next ~30 minutes all had vehicles; later trips simply weren't in the feed yet.
  Entities without a vehicle are treated as *estimated*, not live.
- Predictions can be **out of trip order** (bunching/overtaking): at Lombard & 10th, trip
  964083 was predicted 17 s *after* trip 964081 even though it was scheduled 10 min earlier.
  Always sort by predicted time.
- Buses that are early simply get an earlier predicted time; there is no separate "early"
  flag. TransitView's `late`/`Offset` field gives minutes late per vehicle (negative = early,
  **unverified** for negative values; none observed).

## Vehicle Positions: what the status means

Compared side by side with trip updates (2026-11-18, 25 buses on 40/42):

- `IN_TRANSIT_TO N` means heading to stop sequence N (trip updates list N first).
- `STOPPED_AT N` was reported for 20 of 25 buses, so it isn't literally "stopped". It
  means N is the last stop reached, and trip updates then list N+1 first.
- `current_stop_sequence` uses the same numbering as trip updates.
- Vehicle reports were 12–17 s old at fetch. Trip updates sometimes still listed the
  just-reached stop with a past time (up to ~1 min).

Sparrow uses this for *inferred* arrival windows in validation (see docs/validation.md).

## Directions and stops

From static GTFS `directions.txt` (feed `v202611220`):

| Route | direction_id 0 | direction_id 1 |
|---|---|---|
| 40 | Eastbound → 2nd-Lombard | Westbound → Conshohocken-Monument (some trips 50th-Parkside) |
| 42 | Eastbound → 2nd-Spruce | Westbound → Wycombe or 61st-Pine |

Route 40 runs westbound on Lombard St and eastbound on South St; Route 42 runs westbound on
Walnut St and eastbound on Chestnut St (from `route_stops.txt`). So a Lombard St stop only
exists in Route 40's westbound pattern and a Walnut St stop only in Route 42's westbound
pattern. Sparrow still filters on `direction_id` explicitly.

Stop IDs are verified with `scripts/find_stops.py` against the static GTFS. Examples used in
the committed example config:

| Route | Direction | stop_id | Name |
|---|---|---|---|
| 40 | 1 (Westbound) | 22265 | Lombard St & 10th St |
| 42 | 1 (Westbound) | 14884 | Walnut St & 10th St |

The real commute stops were verified the same way and live only in the private,
gitignored `config/commute.local.toml` (the repository is public).

Stops served by several routes return all of them: Walnut St stops also carry routes 9,
12, and 21. Filtering by `route_id` is mandatory.

## BusSchedules API

- `req2` = route, `req6` = max results. Returns only **future** scheduled times for today.
- Fields: `trip_id`, `Direction` ("1"), `DateCalender` ("11/18/26 05:24 pm", local time),
  `DirectionDesc` (headsign).
- Times are **minute resolution**, so they're coarser than live predictions.
- A very late bus's scheduled time is already "past", so it drops out of BusSchedules while
  still appearing in Trip Updates. Merging must be a union keyed by `trip_id`.

## Static GTFS gotcha

The `latest` release (`v202611220`) is published **ahead** of its start date
(`feed_start_date` 2026-11-22; sampled on 2026-11-18). Today's service isn't in it. Previous
releases weren't reachable from this environment (github.com HTML returned 403). This is
one reason Sparrow uses BusSchedules for scheduled times at runtime instead of loading static
GTFS. Static GTFS is only used offline for stop and direction verification.

## Rate limits and freshness

- No documented rate limits found. The feeds are static files regenerated about every 30 s,
  so polling faster than about 20 s is pointless. Sparrow caches trip updates for 20 s and
  schedules for 5 min, regardless of how many clients poll it.
- Freshness is judged from `header.timestamp` (agency generation time) and per-trip
  `timestamp`, not from whether the HTTP request succeeded.

## Licensing

SEPTA's developer page carries a license agreement for the static "Trip Planning Data"
(non-exclusive, as-is, no commercial use of trademarks, no fee). Real-time feeds are
publicly linked from the same page. Sparrow is personal, non-commercial use.

## Open questions

1. How accurate are the trip-update predictions, especially for early buses? (Milestone 4)
2. Do trip updates ever show a bus predicted *later* than it actually arrives by more than
   the 2-minute buffer? (Milestone 4)
3. How far ahead do vehicles get assigned on weekends and early mornings?
4. Whether negative `late` values (early buses) appear in TransitView.
5. Whether a newer per-stop arrivals API exists. SEPTA's own app may use one, but it isn't
   publicly documented.
