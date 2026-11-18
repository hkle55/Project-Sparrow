# Architecture

## Components

| Module | Responsibility |
|---|---|
| `app/config.py` | Load and validate the TOML commute profile (modes → route options: route, direction, stop, walk time) |
| `app/transit/gtfs_rt.py` | Parse GTFS-RT trip updates. Keep only configured routes and stops. Record trip state (canceled, skipped stops, remaining stops) |
| `app/transit/schedules.py` | Parse BusSchedules JSON (local time → UTC) |
| `app/transit/client.py` | HTTP with timeouts, 2 attempts with backoff, TTL cache (20 s RT, 5 min schedules), last-good fallback, 10 s error backoff |
| `app/predictions/arrivals.py` | Merge live and scheduled data per stop into labeled `Arrival`s |
| `app/recommendations/engine.py` | Pure departure and route-choice logic |
| `app/service.py` | Orchestrate a request and build the compact response |
| `app/simulation.py` | Named synthetic scenarios run through the real engine |
| `app/api/` | FastAPI routes and response schemas. Serves `frontend/` |
| `frontend/` | Static device simulator |

## Data flow for `GET /api/v1/commute/work`

1. `TransitClient.trip_updates()` returns the cached snapshot (refetched if older than
   20 s). If SEPTA fails, it returns the last good snapshot plus the error.
2. `TransitClient.schedule(stop, route)` for each option (5-min cache).
3. `now` is taken *after* fetching.
4. `build_arrivals` for each option:
   - Live predictions for the stop, filtered by route and direction. A bus whose time is
     more than 60 s in the past is dropped.
   - Labeled LIVE (has a vehicle), ESTIMATED (no vehicle), or STALE (feed or trip data
     older than 120 s). Data older than 600 s is ignored.
   - Scheduled trips not already covered by a live prediction are added as SCHEDULED,
     unless the live feed says the trip is canceled, skips this stop, or no longer lists
     it (passed).
5. `recommend` computes `leave_at = at − walk − buffer` for every arrival, classifies it
   ok / tight / missed, and picks the next *ok* bus per route. The preferred route wins
   unless another boards more than the threshold sooner.
6. The response carries epoch times, floored durations, and data status
   (live / stale / offline) plus any upstream error.

## Key decisions and trade-offs

- **Agency predictions, not our own ETA model.** SEPTA's trip updates give per-stop
  predicted times. We don't compute ETAs from GPS distance. Whether that's accurate
  enough is what M4 measures.
- **Passed-stop detection from the feed itself.** SEPTA removes a stop from a trip's
  update once the bus passes. If a trip is in the feed without our stop, it's gone.
- **No static GTFS at runtime.** The 25 MB zip is published ahead of its validity window.
  BusSchedules gives today's timetable with matching trip IDs. Static GTFS is only used
  offline (`scripts/find_stops.py`).
- **Tight buses are shown but not recommended.** The safety buffer exists because buses
  run early. Recommending a bus that eats into it defeats the purpose. (Open product
  question in PROJECT_PLAN.)
- **Floors everywhere.** "Leave in 5m" means at least 5 full minutes. Rounding up could
  cause exactly the missed bus Sparrow exists to prevent.
- **Pure engine.** `now` is injected, so the scenario tests are deterministic, including
  DST and midnight (times are absolute UTC instants internally).
- **On-demand fetch with caching instead of a background poller.** Simpler. SEPTA load is
  bounded by the TTL, not by the number of clients.

## Time handling

GTFS-RT times are POSIX seconds, so they have no timezone ambiguity. BusSchedules gives
local wall-clock date-times. These are parsed in America/New_York, and during the
repeated fall-back hour the earlier instant is chosen (the conservative choice). GTFS
"25:10:00"-style service-day times never reach runtime, because static GTFS isn't loaded.

## Future hardware integration

The ESP32 calls `/api/v1/commute/{mode}` every 15–30 s and renders `rec`
(route / action / leave_at) plus three `at` times per route. It counts down locally
using `now` for skew. If a poll fails, it shows NO CONNECTION after ~45 s and keeps the
countdown marked as unreliable. The device does no transit logic. Deployment (M5) adds
HTTPS and a device token.
