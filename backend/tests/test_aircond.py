"""Aircond fan speed and modes, on/off timers, and default device names."""

from datetime import timedelta

import pytest

from nestra.simulator import Home, SimClock
from nestra.simulator.home import DEFAULT_CONFIG


@pytest.fixture
def night_home() -> Home:
    return Home.from_file(DEFAULT_CONFIG, clock=SimClock.at_hour(21.5))


def test_aircond_fan_speed_by_voice(processor, home):
    result = processor.execute("set the bedroom aircond fan to high")
    ac = home.devices["bedroom_ac"]
    assert result.ok and ac.fan_speed == "high" and ac.on
    assert home.activity[0].changes[0].label == "Fan speed"
    # The ceiling fan in the same room is untouched.
    assert not home.devices["bedroom_ceiling_fan"].on


def test_aircond_fan_steps_up_and_down(processor, home):
    home.update_device("office_ac", {"fan_speed": "low"})
    processor.execute("turn up the office aircond fan")
    assert home.devices["office_ac"].fan_speed == "medium"
    processor.execute("turn down the office aircond fan")
    assert home.devices["office_ac"].fan_speed == "low"


@pytest.mark.parametrize(
    "text, mode",
    [
        ("switch the bedroom aircond to dry mode", "dry"),
        ("set the bedroom ac mode to heat", "heat"),
        ("put the bedroom aircond in fan mode", "fan"),
        ("dehumidify the bedroom", "dry"),
    ],
)
def test_aircond_modes(processor, home, text, mode):
    assert processor.execute(text).ok
    assert home.devices["bedroom_ac"].mode == mode


def test_timer_relative_and_firing(night_home):
    from nestra.commands import CommandProcessor

    p = CommandProcessor(night_home)
    night_home.update_device("bedroom_ac", {"on": True})
    result = p.execute("turn off the bedroom aircond in 2 hours")
    assert "23:30" in result.reply
    ac = night_home.devices["bedroom_ac"]
    assert ac.on and ac.timer_off_at is not None

    # Nothing happens before it's due.
    assert night_home.run_timers() == []
    # Move the clock past the timer.
    night_home.clock._start += timedelta(hours=2, minutes=1)
    assert night_home.run_timers() == ["bedroom_ac"]
    ac = night_home.devices["bedroom_ac"]
    assert not ac.on and ac.timer_off_at is None
    entry = night_home.activity[0]
    assert entry.source == "timer" and entry.changes[0].new_text == "Off"


def test_timer_at_clock_time_rolls_to_tomorrow(night_home):
    from nestra.commands import CommandProcessor

    result = CommandProcessor(night_home).execute("turn on the bedroom ac at 7am")
    assert "07:00 tomorrow" in result.reply
    due = night_home.devices["bedroom_ac"].timer_on_at
    assert due is not None and due.endswith("T07:00:00")


def test_on_for_a_while_then_off(processor, home):
    result = processor.execute("turn on the bedroom fan for 30 minutes")
    fan = home.devices["bedroom_ceiling_fan"]
    assert result.ok and fan.on and fan.timer_off_at is not None


def test_cancel_timer(processor, home):
    processor.execute("turn off the office aircond in 1 hour")
    assert home.devices["office_ac"].timer_off_at
    processor.execute("cancel the office aircond timer")
    assert home.devices["office_ac"].timer_off_at is None


def test_dry_mode_dries_more_than_cool(home):
    for mode in ("cool", "dry"):
        h = Home.from_file(DEFAULT_CONFIG, clock=SimClock.at_hour(14))
        h.update_device("bedroom_ac", {"on": True, "mode": mode, "setpoint": 24})
        start = h.rooms["bedroom"].environment.humidity
        for _ in range(10):
            h.tick(1)
        drop = start - h.rooms["bedroom"].environment.humidity
        if mode == "cool":
            cool_drop = drop
        else:
            assert drop > cool_drop


def test_fan_mode_does_not_cool(home):
    home.update_device("bedroom_ac", {"on": True, "mode": "fan", "setpoint": 18})
    outside = home.outside_temperature()
    start = home.rooms["bedroom"].environment.temperature
    home.tick(10)
    t = home.rooms["bedroom"].environment.temperature
    # Only drifts toward outside; no aircond cooling.
    assert abs(t - start) <= abs(outside - start)
    assert t >= min(start, outside) - 1e-9


def test_high_fan_cools_faster_than_low():
    drops = {}
    for speed in ("low", "high"):
        h = Home.from_file(DEFAULT_CONFIG, clock=SimClock.at_hour(14))
        h.update_device("bedroom_ac", {"on": True, "fan_speed": speed, "setpoint": 18})
        start = h.rooms["bedroom"].environment.temperature
        h.tick(5)
        drops[speed] = start - h.rooms["bedroom"].environment.temperature
    assert drops["high"] > drops["low"]


def test_default_names(home):
    a = home.add_device("ac", "", "kitchen")
    b = home.add_device("ac", None, "kitchen")
    tv = home.add_device("appliance", " ", "kitchen", kind="tv")
    assert (a.name, b.name, tv.name) == ("Aircond", "Aircond 2", "TV")


def test_api_timer_by_minutes_and_clock_time(tmp_path):
    from fastapi.testclient import TestClient

    from nestra.main import Settings, create_app

    s = Settings(start_hour=21.5, time_scale=0, state_file=tmp_path / "home.json")
    with TestClient(create_app(settings=s, simulate=False)) as client:
        d = client.patch("/api/devices/bedroom_ac", json={"timer_off_in": 90}).json()["device"]
        assert d["timer_off_at"].endswith("T23:00:00")
        d = client.patch("/api/devices/bedroom_ac", json={"timer_on_at_time": "07:30"}).json()["device"]
        assert d["timer_on_at"].endswith("T07:30:00")
        d = client.patch("/api/devices/bedroom_ac", json={"timer_off_at": None, "timer_on_at": None}).json()["device"]
        assert d["timer_off_at"] is None and d["timer_on_at"] is None
        assert client.patch("/api/devices/bedroom_ac", json={"timer_off_in": "soon"}).status_code == 422
        d = client.patch("/api/devices/bedroom_ac", json={"fan_speed": "high", "mode": "dry"}).json()["device"]
        assert (d["fan_speed"], d["mode"]) == ("high", "dry")
