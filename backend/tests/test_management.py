"""Adding/editing/removing rooms and devices, appliances, activity entries, saving."""

import pytest
from fastapi.testclient import TestClient

from nestra.main import Settings, create_app
from nestra.store import JsonFileStore


def test_activity_entry_shows_before_and_after(processor, home):
    processor.execute("set the living room fan to medium")
    entry = home.activity[0]
    assert entry.title == "Air Circulator" and entry.room_name == "Living Room"
    assert entry.command == "set the living room fan to medium"
    [change] = entry.changes
    assert change.label == "Fan speed"
    assert change.old_text == "High (85%)" and change.new_text.startswith("Medium")


def test_turning_on_lists_main_change_first(processor, home):
    processor.execute("set the bedroom fan to high")
    labels = [c.label for c in home.activity[0].changes]
    assert labels == ["Fan speed", "Power"]


def test_add_appliance_and_control_it_by_alias(processor, home):
    tv = home.add_device("appliance", "TV", "living_room", kind="tv")
    result = processor.execute("turn on the television", room_context="living_room")
    assert result.ok and home.devices[tv.id].on


def test_same_appliance_in_two_rooms_asks_which(processor, home):
    home.add_device("appliance", "TV", "living_room", kind="tv")
    home.add_device("appliance", "Bedroom TV", "bedroom", kind="tv")
    result = processor.execute("turn on the tv", room_context="kitchen")
    assert result.needs_clarification
    assert {o["room_id"] for o in result.options} == {"living_room", "bedroom"}
    # The tablet's room settles it.
    result = processor.execute("turn on the tv", room_context="bedroom")
    assert [c.device_name for c in result.changes] == ["Bedroom TV"]


def test_new_device_name_is_understood(processor, home):
    home.add_device("light", "Fairy Lights", "bedroom")
    result = processor.execute("turn on the fairy lights")
    assert result.ok and result.changes[0].device_name == "Fairy Lights"


def test_room_management(home):
    room = home.add_room("Garage")
    assert room.id == "garage" and room.name == "Garage"
    with pytest.raises(ValueError):
        home.add_room("garage")
    home.add_device("appliance", "Charger", "garage", kind="charger")
    home.rename_room("garage", "Car Port")
    assert home.rooms["garage"].name == "Car Port"
    removed = home.remove_room("garage")
    assert len(removed) == 1 and "garage" not in home.rooms


def test_duplicate_device_name_in_room_rejected(home):
    with pytest.raises(ValueError):
        home.add_device("light", "reading lamp", "living_room")


def test_api_crud_and_persistence(tmp_path):
    settings = Settings(start_hour=14, time_scale=0, state_file=tmp_path / "home.json")
    with TestClient(create_app(settings=settings, simulate=False)) as client:
        catalog = client.get("/api/catalog").json()
        assert {"type": "appliance", "label": "Appliance"} in catalog["device_types"]

        room = client.post("/api/rooms", json={"name": "Garage"}).json()
        device = client.post(
            "/api/devices", json={"type": "appliance", "name": "Kettle", "room_id": "kitchen", "kind": "kettle"}
        ).json()
        assert client.post("/api/devices", json={"type": "toaster", "name": "X", "room_id": "kitchen"}).status_code == 422
        assert client.post("/api/devices", json={"type": "light", "name": "X", "room_id": "nowhere"}).status_code == 404

        r = client.patch(f"/api/devices/{device['id']}", json={"name": "Electric Kettle", "on": True})
        assert r.status_code == 200
        labels = {c["label"] for c in client.get("/api/activity").json()[0]["changes"]}
        assert labels == {"Name", "Power"}

        r = client.post("/api/command", json={"text": "turn off the kettle"})
        assert r.json()["ok"]

    saved = JsonFileStore(settings.state_file).load()
    assert saved is not None
    assert any(r.id == room["id"] for r in saved.rooms)
    kettle = next(d for d in saved.devices if d.name == "Electric Kettle")
    assert kettle.on is False

    # A new app picks up the saved home.
    with TestClient(create_app(settings=settings, simulate=False)) as client:
        names = {d["name"] for r in client.get("/api/home").json()["rooms"] for d in r["devices"]}
        assert "Electric Kettle" in names
