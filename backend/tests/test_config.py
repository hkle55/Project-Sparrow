from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from app.config import EXAMPLE_CONFIG, ConfigError, load_config, parse_config


def test_example_config_loads():
    cfg = load_config(EXAMPLE_CONFIG)
    work = cfg.modes["work"]
    assert work.configured
    assert [o.route for o in work.options] == ["40", "42"]
    assert work.preferred_route == "40"
    assert cfg.settings.safety_buffer_min == 2.0


def test_home_mode_unconfigured_in_example():
    assert not load_config(EXAMPLE_CONFIG).modes["home"].configured


def test_env_var_selects_config(tmp_path, monkeypatch):
    p = tmp_path / "c.toml"
    p.write_text('[modes.work]\nlabel = "W"\n')
    monkeypatch.setenv("SPARROW_CONFIG", str(p))
    cfg = load_config()
    assert cfg.source == str(p) and not cfg.modes["work"].configured


def test_inline_toml_env_var_wins(monkeypatch):
    monkeypatch.setenv("SPARROW_CONFIG_TOML", '[modes.work]\nlabel = "Inline"\n')
    cfg = load_config()
    assert cfg.source == "$SPARROW_CONFIG_TOML" and cfg.modes["work"].label == "Inline"


def test_inline_json_env_var(monkeypatch):
    monkeypatch.setenv("SPARROW_CONFIG_JSON", '{"modes": {"work": {"label": "J", "options": ['
                       '{"route": "40", "direction_id": 1, "stop_id": "9", "walk_min": 3}]}}}')
    cfg = load_config()
    assert cfg.source == "$SPARROW_CONFIG_JSON"
    assert cfg.modes["work"].options[0].stop_id == "9"


@pytest.mark.parametrize("bad", ["{nope", "[1, 2]"])
def test_inline_json_invalid(monkeypatch, bad):
    monkeypatch.setenv("SPARROW_CONFIG_JSON", bad)
    with pytest.raises(ConfigError):
        load_config()


def test_inline_toml_invalid(monkeypatch):
    monkeypatch.setenv("SPARROW_CONFIG_TOML", "this is = = not toml")
    with pytest.raises(ConfigError):
        load_config()


def opt(**kw):
    base = {"route": "40", "direction_id": 1, "stop_id": "1", "walk_min": 4}
    base.update(kw)
    return base


@pytest.mark.parametrize(
    "data",
    [
        {"settings": {"bogus": 1}},
        {"modes": {"w": {"options": [{"route": "40"}]}}},
        {"modes": {"w": {"options": [opt(walk_min=-1)]}}},
        {"modes": {"w": {"options": [opt(direction_id=2)]}}},
        {"modes": {"w": {"preferred_route": "99", "options": [opt()]}}},
        {"settings": {"timezone": "Mars/Olympus"}},
        {"settings": {"home_after": "2pm"}},
        {"settings": {"work_after": "15:00", "home_after": "14:00"}},
    ],
)
def test_invalid_configs_rejected(data):
    with pytest.raises(ConfigError):
        parse_config(data)


# --- auto mode: work in the morning window, home the rest of the day -----------------------

NY = ZoneInfo("America/New_York")
BOTH = {
    "modes": {
        "work": {"options": [opt(stop_id="w")]},
        "home": {"options": [opt(stop_id="h", direction_id=0)]},
    }
}


def at(hour, minute=0):
    return datetime(2026, 11, 18, hour, minute, tzinfo=NY)


@pytest.mark.parametrize(
    ("when", "expected"),
    [
        (at(2, 59), "home"),   # late night still counts as going home
        (at(3, 0), "work"),
        (at(8, 30), "work"),
        (at(13, 59), "work"),
        (at(14, 0), "home"),
        (at(18, 0), "home"),
        (at(23, 59), "home"),
    ],
)
def test_auto_mode_by_time_of_day(when, expected):
    assert parse_config(BOTH).auto_mode(when).key == expected


def test_auto_mode_uses_eastern_time_whatever_the_input_zone():
    utc_noon = datetime(2026, 11, 18, 17, 0, tzinfo=ZoneInfo("UTC"))  # 12:00 pm ET
    assert parse_config(BOTH).auto_mode(utc_noon).key == "work"


def test_auto_mode_cutoff_is_configurable():
    cfg = parse_config({**BOTH, "settings": {"home_after": "16:30"}})
    assert cfg.auto_mode(at(16, 0)).key == "work"
    assert cfg.auto_mode(at(16, 30)).key == "home"


def test_auto_mode_falls_back_when_home_not_set_up():
    cfg = load_config(EXAMPLE_CONFIG)  # home has no options
    assert cfg.auto_mode(at(18, 0)).key == "work"


def test_auto_mode_with_no_modes():
    assert parse_config({}).auto_mode(at(9, 0)) is None
