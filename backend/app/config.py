"""Commute profile loading.

The profile is TOML. For hosting, put the whole file's contents in the secret
``$SPARROW_CONFIG_TOML``. Locally, the real one (with the actual commute stops) lives in
``config/commute.local.toml`` or wherever ``$SPARROW_CONFIG`` points. It is gitignored
because the repository is public. ``config/commute.example.toml`` is the committed
fallback.
"""

from __future__ import annotations

import json
import os
import tomllib
from dataclasses import dataclass, field
from datetime import datetime, time
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

REPO_ROOT = Path(__file__).resolve().parents[2]
LOCAL_CONFIG = REPO_ROOT / "config" / "commute.local.toml"
EXAMPLE_CONFIG = REPO_ROOT / "config" / "commute.example.toml"


class ConfigError(ValueError):
    pass


@dataclass(frozen=True)
class RouteOption:
    """One way to make the trip: board `route` at `stop_id` heading `direction_id`."""

    route: str
    direction_id: int
    stop_id: str
    stop_name: str
    walk_min: float


@dataclass(frozen=True)
class CommuteMode:
    key: str
    label: str
    preferred_route: str | None
    options: tuple[RouteOption, ...]

    @property
    def configured(self) -> bool:
        return len(self.options) > 0


@dataclass(frozen=True)
class Settings:
    timezone: str = "America/New_York"
    safety_buffer_min: float = 2.0
    preference_threshold_min: float = 5.0
    get_ready_window_min: float = 3.0
    tight_max_wait_min: float = 10.0
    stale_after_s: int = 120
    discard_after_s: int = 600
    arrivals_per_route: int = 3
    # Auto mode (local time, HH:MM): the work commute from work_after until home_after,
    # the home commute the rest of the day (including after midnight).
    work_after: str = "03:00"
    home_after: str = "14:00"

    @property
    def tz(self) -> ZoneInfo:
        return ZoneInfo(self.timezone)


@dataclass(frozen=True)
class SparrowConfig:
    settings: Settings
    modes: dict[str, CommuteMode] = field(default_factory=dict)
    source: str = ""

    def auto_mode(self, now: datetime) -> CommuteMode | None:
        """The commute to show at `now`: work in the morning window, home otherwise.
        Falls back to any configured mode if the one for this time isn't set up."""
        local = now.astimezone(self.settings.tz).time()
        work_from = _hhmm(self.settings.work_after, "work_after")
        home_from = _hhmm(self.settings.home_after, "home_after")
        want = "work" if work_from <= local < home_from else "home"
        ordered = sorted(self.modes.values(), key=lambda m: m.key != want)
        for m in ordered:
            if m.configured:
                return m
        return ordered[0] if ordered else None


def _hhmm(value: str, name: str) -> time:
    try:
        hours, minutes = value.split(":")
        return time(int(hours), int(minutes))
    except ValueError as exc:
        raise ConfigError(f"settings.{name} must be HH:MM, got {value!r}") from exc


def _parse_option(raw: dict, where: str) -> RouteOption:
    try:
        opt = RouteOption(
            route=str(raw["route"]),
            direction_id=int(raw["direction_id"]),
            stop_id=str(raw["stop_id"]),
            stop_name=str(raw.get("stop_name", raw["stop_id"])),
            walk_min=float(raw["walk_min"]),
        )
    except KeyError as exc:
        raise ConfigError(f"{where}: missing field {exc}") from exc
    if opt.walk_min < 0:
        raise ConfigError(f"{where}: walk_min must be >= 0")
    if opt.direction_id not in (0, 1):
        raise ConfigError(f"{where}: direction_id must be 0 or 1")
    return opt


def parse_config(data: dict, source: str = "<memory>") -> SparrowConfig:
    known = set(Settings.__dataclass_fields__)
    raw_settings = data.get("settings", {})
    unknown = set(raw_settings) - known
    if unknown:
        raise ConfigError(f"unknown settings: {sorted(unknown)}")
    settings = Settings(**raw_settings)
    try:
        ZoneInfo(settings.timezone)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise ConfigError(f"unknown timezone {settings.timezone!r}") from exc
    if _hhmm(settings.work_after, "work_after") >= _hhmm(settings.home_after, "home_after"):
        raise ConfigError("settings.work_after must be earlier than settings.home_after")

    modes: dict[str, CommuteMode] = {}
    for key, raw_mode in data.get("modes", {}).items():
        options = tuple(
            _parse_option(o, f"modes.{key}.options[{i}]")
            for i, o in enumerate(raw_mode.get("options", []))
        )
        preferred = raw_mode.get("preferred_route")
        if preferred is not None and options and preferred not in {o.route for o in options}:
            raise ConfigError(f"modes.{key}: preferred_route {preferred!r} has no option")
        modes[key] = CommuteMode(
            key=key,
            label=str(raw_mode.get("label", key)),
            preferred_route=str(preferred) if preferred is not None else None,
            options=options,
        )
    return SparrowConfig(settings=settings, modes=modes, source=source)


def config_path() -> Path:
    env = os.environ.get("SPARROW_CONFIG")
    if env:
        path = Path(env)
        return path if path.is_absolute() else REPO_ROOT / path
    return LOCAL_CONFIG if LOCAL_CONFIG.exists() else EXAMPLE_CONFIG


def load_config(path: Path | None = None) -> SparrowConfig:
    """Load the profile from `path`, else from the *contents* in $SPARROW_CONFIG_TOML or
    $SPARROW_CONFIG_JSON (single-line form, for hosts and cloud environments that only allow
    one-line variables), else $SPARROW_CONFIG / local / example file."""
    if path is None and (inline := os.environ.get("SPARROW_CONFIG_JSON")):
        try:
            data = json.loads(inline)
        except ValueError as exc:
            raise ConfigError(f"SPARROW_CONFIG_JSON is not valid JSON: {exc}") from exc
        if not isinstance(data, dict):
            raise ConfigError("SPARROW_CONFIG_JSON must be a JSON object")
        return parse_config(data, source="$SPARROW_CONFIG_JSON")
    if path is None and (inline := os.environ.get("SPARROW_CONFIG_TOML")):
        try:
            data = tomllib.loads(inline)
        except tomllib.TOMLDecodeError as exc:
            raise ConfigError(f"SPARROW_CONFIG_TOML is not valid TOML: {exc}") from exc
        return parse_config(data, source="$SPARROW_CONFIG_TOML")
    path = path or config_path()
    with open(path, "rb") as fh:
        return parse_config(tomllib.load(fh), source=str(path))
