"""Fetch SEPTA data with caching, timeouts, bounded retries, and last-good fallback.

One TransitClient is shared by the whole app. However many browsers or devices poll
Sparrow, SEPTA sees at most one trip-updates request per `tu_ttl` seconds.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

import httpx

from .gtfs_rt import TRIP_UPDATES_URL, parse_trip_updates
from .models import ScheduledArrival, TransitDataError, TripUpdatesSnapshot
from .schedules import BUS_SCHEDULES_URL, parse_bus_schedules, schedule_params

log = logging.getLogger(__name__)

USER_AGENT = "Sparrow/0.1 (personal transit display)"


@dataclass
class CacheEntry:
    value: object | None = None
    fetched_at: float = 0.0  # monotonic, for TTL
    fetched_wall: datetime | None = None  # when we last *successfully* fetched
    error: str | None = None  # last failure, cleared on success
    error_at: datetime | None = None


@dataclass(frozen=True)
class Fetched:
    value: object | None
    fetched_at: datetime | None
    error: str | None


class TransitClient:
    def __init__(
        self,
        routes: Iterable[str],
        stop_ids: Iterable[str],
        tz: ZoneInfo,
        *,
        http: httpx.AsyncClient | None = None,
        tu_ttl: float = 20.0,
        schedule_ttl: float = 300.0,
        error_retry_after: float = 10.0,
        attempts: int = 2,
        timeout: float = 8.0,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self.routes = set(routes)
        self.stop_ids = set(stop_ids)
        self.tz = tz
        self.http = http or httpx.AsyncClient(
            timeout=httpx.Timeout(timeout), headers={"User-Agent": USER_AGENT}
        )
        self.tu_ttl = tu_ttl
        self.schedule_ttl = schedule_ttl
        self.error_retry_after = error_retry_after
        self.attempts = attempts
        self.clock = clock
        self.monotonic = monotonic
        self._entries: dict[str, CacheEntry] = {}
        self._locks: dict[str, asyncio.Lock] = {}

    async def aclose(self) -> None:
        await self.http.aclose()

    async def _get(self, url: str, params: dict | None = None) -> httpx.Response:
        last: Exception | None = None
        for attempt in range(self.attempts):
            try:
                resp = await self.http.get(url, params=params)
                if resp.status_code == 200:
                    return resp
                last = TransitDataError(f"HTTP {resp.status_code} from {url}")
                if resp.status_code < 500 and resp.status_code != 429:
                    break  # a 4xx won't fix itself on retry
            except httpx.HTTPError as exc:
                last = TransitDataError(f"{type(exc).__name__} contacting {url}")
            if attempt + 1 < self.attempts:
                await asyncio.sleep(0.5 * 2**attempt)
        assert last is not None
        raise last

    async def _cached(self, key: str, ttl: float, load: Callable) -> Fetched:
        entry = self._entries.setdefault(key, CacheEntry())
        lock = self._locks.setdefault(key, asyncio.Lock())
        async with lock:
            age = self.monotonic() - entry.fetched_at
            fresh = entry.value is not None and age < ttl
            # After a failure, back off before hammering the upstream again.
            backing_off = (
                entry.error is not None
                and entry.error_at is not None
                and (self.clock() - entry.error_at).total_seconds() < self.error_retry_after
            )
            if not fresh and not backing_off:
                try:
                    entry.value = await load()
                    entry.fetched_at = self.monotonic()
                    entry.fetched_wall = self.clock()
                    entry.error = None
                    entry.error_at = None
                except (TransitDataError, ValueError) as exc:
                    log.warning("fetch %s failed: %s", key, exc)
                    entry.error = str(exc)
                    entry.error_at = self.clock()
            return Fetched(entry.value, entry.fetched_wall, entry.error)

    async def trip_updates(self) -> Fetched:
        async def load() -> TripUpdatesSnapshot:
            resp = await self._get(TRIP_UPDATES_URL)
            return parse_trip_updates(resp.content, self.routes, self.stop_ids)

        return await self._cached("trip_updates", self.tu_ttl, load)

    async def schedule(self, stop_id: str, route: str, count: int = 8) -> Fetched:
        async def load() -> list[ScheduledArrival]:
            resp = await self._get(BUS_SCHEDULES_URL, schedule_params(stop_id, route, count))
            try:
                payload = resp.json()
            except ValueError as exc:
                raise TransitDataError("BusSchedules returned invalid JSON") from exc
            return parse_bus_schedules(payload, route, stop_id, self.tz)

        return await self._cached(f"schedule:{stop_id}:{route}", self.schedule_ttl, load)
