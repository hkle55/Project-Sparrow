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
    ],
)
def test_invalid_configs_rejected(data):
    with pytest.raises(ConfigError):
        parse_config(data)
