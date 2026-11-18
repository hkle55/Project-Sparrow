# Handoff

_Last updated: 2026-11-18, end of Milestone 3._

## Status

Milestones 0–3 are complete: a local web prototype runs on live SEPTA data. Milestone 4
(prediction validation) is next.

## Branches and PRs

- `main`: stable. M0 (PR #1) and M1 (PR #2) are merged.
- `feat/commute-recommendations`: M2, PR #3.
- `feat/device-simulator`: M3 (branched from M2), PR #4.

## Tests

- `cd backend && ../.venv/bin/pytest -q`: 102 passed (offline)
- `pytest -m live`: 1 passed against SEPTA on 2026-11-18
- `ruff check .`: clean
- Manual browser check (Chromium via Playwright): live mode, all 8 scenarios, home mode,
  simulated connection loss, mobile (iPhone 13) and desktop layouts, no console errors.

## Local setup gotcha

The real commute profile is `config/commute.local.toml`, which is gitignored. A fresh
cloud container won't have it: recreate it from the example with the real stops (ask
the product owner, or check `docs/private/` if present locally). Without it, the app
runs on the example stops.

## Blockers / needs owner input

- Home commute stop and walk time are unknown.
- Product decision: should a "tight" preferred bus be recommended as HURRY?
- The repo is public. Keep real stops out of git.

## Next steps (M4)

1. Observation logger: every 30 s, record the trip-update predictions for the configured
   stops to SQLite under `data/` (gitignored). Record the inferred arrival when a trip
   drops the stop.
2. Manual observation entry for ground truth.
3. Report: prediction error by lead time, early-arrival rate, staleness frequency,
   buffer sufficiency.
