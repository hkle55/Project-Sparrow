"""Commute profile loading.

The profile is a TOML file. The real one (with the actual commute stops) lives in
``config/commute.local.toml`` or wherever ``$SPARROW_CONFIG`` points. It is gitignored
because the repository is public. ``config/commute.example.toml`` is the committed
fallback.
"""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field
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
    stale_after_s: int = 120
    discard_after_s: int = 600
    arrivals_per_route: int = 3

    @property
    def tz(self) -> ZoneInfo:
        return ZoneInfo(self.timezone)


@dataclass(frozen=True)
class SparrowConfig:
    settings: Settings
    modes: dict[str, CommuteMode] = field(default_factory=dict)
    source: str = ""


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
    path = path or config_path()
    with open(path, "rb") as fh:
        return parse_config(tomllib.load(fh), source=str(path))
