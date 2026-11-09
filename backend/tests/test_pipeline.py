from fastapi.testclient import TestClient

from nestra.main import Settings, create_app


def test_comfortable_fan_lowers_speed_with_explanation(processor, home):
    before = home.devices["living_air_circulator"].speed
    result = processor.execute("lower the fan to a comfortable speed", room_context="living_room")
    after = home.devices["living_air_circulator"].speed
    assert result.ok and after < before
    assert result.explanations[0]["system"] == "fan_comfort"
    assert result.explanations[0]["rules"]


def test_comfort_respects_direction(processor, home):
    home.update_device("living_air_circulator", {"speed": 20})
    result = processor.execute("lower the fan to a comfortable speed", room_context="living_room")
    assert result.ok and not result.changes
    assert "already" in result.reply


def test_ambiguous_device_asks_which(processor):
    result = processor.execute("make it a bit warmer", room_context="kitchen")
    assert result.needs_clarification
    assert {o["room_id"] for o in result.options} == {"bedroom", "office"}


def test_relative_step_is_small_for_a_bit(processor, home):
    result = processor.execute("make the office a bit warmer")
    assert result.ok
    change = result.changes[0]
    assert 0.5 <= change.new - change.old <= 2


def test_unlock_needs_confirmation(processor, home):
    result = processor.execute("unlock the front door")
    assert result.needs_confirmation and home.devices["front_door"].locked
    result = processor.execute("unlock the front door", confirm=True)
    assert result.ok and not home.devices["front_door"].locked


def test_named_level_and_activity_log(processor, home):
    result = processor.execute("set the bedroom fan to high")
    fan = home.devices["bedroom_ceiling_fan"]
    assert result.ok and fan.on and 70 <= fan.speed <= 90
    assert home.activity[0].source == "voice"


def test_ac_cools_room_over_time(home):
    home.update_device("bedroom_ac", {"on": True, "setpoint": 22})
    start = home.rooms["bedroom"].environment.temperature
    for _ in range(30):
        home.tick(1)
    assert home.rooms["bedroom"].environment.temperature < start - 1


def test_api_and_websocket(tmp_path):
    settings = Settings(start_hour=14, time_scale=0, state_file=tmp_path / "home.json")
    app = create_app(settings=settings, simulate=False)
    with TestClient(app) as client:
        assert client.get("/api/home").json()["rooms"]
        r = client.post("/api/command", json={"text": "turn off the lights"})
        assert r.status_code == 200 and r.json()["ok"]
        r = client.patch("/api/devices/living_main_ceiling", json={"brightness": 500})
        assert r.status_code == 422
        r = client.post("/api/fuzzy/fan_comfort", json={"inputs": {"temperature": 30, "humidity": 70}})
        assert r.json()["term"] in ("high", "max")

        with client.websocket_connect("/ws") as ws:
            assert ws.receive_json()["type"] == "snapshot"
            ws.send_json({"type": "command", "text": "turn on the reading lamp"})
            seen = set()
            while "command_result" not in seen:
                seen.add(ws.receive_json()["type"])
            assert "device" in seen


def test_everything_in_this_room_and_whole_home():
    from nestra.commands import CommandProcessor
    from nestra.simulator import Home, SimClock
    from nestra.simulator.home import DEFAULT_CONFIG

    home = Home.from_file(DEFAULT_CONFIG, clock=SimClock.at_hour(14, scale=0))
    cp = CommandProcessor(home)
    r = cp.execute("turn off everything in here", room_context="bedroom")
    assert r.ok and "in the Bedroom" in r.reply
    assert all(not d.on for d in home.devices.values() if d.room_id == "bedroom" and hasattr(d, "on"))
    assert any(d.on for d in home.devices.values() if d.room_id != "bedroom" and hasattr(d, "on"))
    again = cp.execute("turn off everything in here", room_context="bedroom")
    assert again.ok and "already off" in again.reply and not again.changes
    r = cp.execute("shut down everything", room_context="bedroom")
    assert r.ok and all(not d.on for d in home.devices.values() if hasattr(d, "on"))
