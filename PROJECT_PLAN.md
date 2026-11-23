# Sparrow Project Plan

## V1 scope (owner decision 2026-11-18)

**V1 = a physical Sparrow for the morning commute to work, only.**

- Route 40 (preferred) and Route 42 at her real stops, which live only in the private config.
  Next three arrivals for each.
- Keep the existing recommendation engine, 2-min safety buffer, and tight-connection logic.
- Prioritize instant access to the countdown.
- No work/home toggle on the device. The backend keeps home-mode support for later.
- The return commute is **out of scope** and is not a blocker.
- The device only needs her home Wi-Fi. Workplace Wi-Fi is not a V1 requirement.
- Workstreams in parallel: deployment, prediction collection, hardware selection,
  firmware preparation.

## Current milestone

**Parallel:** M5 deploy (awaiting spend approval), M4 data collection (starts at deploy),
M6 hardware selection (recommendation ready), M7 firmware preparation.

## Milestones

| # | Milestone | Status |
|---|---|---|
| 0 | Project initialization | Done |
| 1 | SEPTA research and data retrieval | Done |
| 2 | Prediction and recommendation engine and API | Done |
| 3 | Web device simulator | Done (local) |
| 4 | Prediction validation (observation logging and report) | Tooling done; collecting data |
| 5 | Remote deployment (research and recommendation, no paid infra without approval) | Prepared; awaiting approval to spend ~$2–3/mo |
| 6 | Hardware research and BOM (no purchases without approval) | In progress |
| 7 | ESP32 firmware | Preparing (device API + firmware core) |
| 8 | Battery and physical product | Not started |

## Acceptance criteria (abridged; full text in the master spec)

- **M1**: terminal shows the next 3 westbound arrivals for Route 40 and Route 42 at the
  configured stops. Live and scheduled are distinguished, wrong-direction buses are
  excluded, and parsing is tested.
- **M2**: deterministic tests for the recommendation table, early and missed buses, and
  stale data. Route 40 preference is configurable. Unconfigured home mode is handled.
  API responses are compact.
- **M3**: simulator runs on real data, updates without a manual refresh, works on mobile,
  has a labeled simulation mode, and shows a home-mode "not configured" state.
- **M4**: logged predictions vs. observed arrivals. The report gives error and early-bus
  frequency and says whether the buffer is sufficient.

## Blockers

- None for M4.
- Simulator acceptance item "works on mobile" is verified only in emulation. Real-phone
  use needs hosting (M5).

## Unresolved technical questions

- Prediction accuracy of SEPTA trip updates, especially for early buses (M4 answers this).
- Ground truth for "the bus actually arrived": SEPTA removes the stop from the trip update
  once the bus passes. That gives an *inferred* arrival time with ~30 s resolution. Manual
  observations are needed for independent truth.
- How far ahead vehicles are assigned to trips in early mornings and weekends.
- Static GTFS releases are published before their start date. A future static-schedule
  fallback must pick the release that covers today.

## Open product decisions

1. Route comparison basis. Today: boarding time with a 5-minute preference for Route 40.
   Later: total door-to-door time, once destination stops and walk times are known.
2. ~~Tight buses~~ Decided 2026-11-18: TIGHT CONNECTION state, recommended only when no
   safe bus boards within 10 min after it.
3. Hosting choice (M5) and whether the web app needs a login, or just an unguessable
   URL or token.
4. ~~Repo visibility~~ Decided 2026-11-18: stays public. Personal config and observation
   logs stay out of git.
