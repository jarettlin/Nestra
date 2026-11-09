import pytest

from nestra.nlu import CommandParser, DeviceRef, RoomRef


@pytest.fixture
def parser(home):
    return CommandParser(
        [RoomRef(r.id, [r.name, *r.aliases]) for r in home.rooms.values()],
        [DeviceRef(d.id, d.name, d.type, d.room_id) for d in home.devices.values()],
    )


@pytest.mark.parametrize(
    "text, expected",
    [
        ("lower the fan speed to a comfortable speed", dict(action="decrease", device_types=["fan"], term="comfortable")),
        ("set the bedroom AC to 24°C", dict(action="set", device_ids=["bedroom_ac"], value=24.0)),
        ("make it a bit warmer", dict(action="increase", device_types=["ac"], hedge="small")),
        ("dim the lights", dict(action="decrease", device_types=["light"], term=None)),
        ("set the lights to dim", dict(action="set", device_types=["light"], term="dim")),
        ("turn on the reading lamp", dict(action="on", device_ids=["living_reading_lamp"])),
        ("turn on the redding lamp", dict(action="on", device_ids=["living_reading_lamp"])),
        ("close the shades", dict(action="close", device_types=["blinds"])),
        ("unlock the front door", dict(action="unlock", device_ids=["front_door"])),
        ("turn off the lights and fan", dict(action="off", device_types=["light", "fan"])),
        ("turn off all the lights", dict(action="off", all_scope=True)),
        ("turn up the fan a lot", dict(action="increase", hedge="large")),
        ("increase the brightness by 10", dict(action="increase", device_types=["light"], delta=10.0)),
        ("make the bedroom cozy", dict(action="set", device_types=[], room_ids=["bedroom"], term="comfortable")),
        ("set the fan on low", dict(action="set", term="low")),
    ],
)
def test_parse_single(parser, text, expected):
    [cmd] = parser.parse(text)
    for key, value in expected.items():
        assert getattr(cmd, key) == value, f"{key}: {getattr(cmd, key)!r} != {value!r}"


def test_bedroom_fan_does_not_match_bedroom_ac(parser):
    [cmd] = parser.parse("turn on the bedroom fan")
    assert cmd.device_types == ["fan"] and cmd.device_ids == [] and cmd.room_ids == ["bedroom"]


def test_compound_command_inherits_target(parser):
    first, second = parser.parse("turn on the bedroom fan and set it to low")
    assert first.action == "on" and second.action == "set"
    assert second.device_types == ["fan"] and second.room_ids == ["bedroom"]
    assert second.term == "low"


def test_nonsense_parses_to_nothing(parser):
    assert parser.parse("hello there") == []


def test_everything_commands():
    from nestra.nlu import CommandParser, DeviceRef, RoomRef

    p = CommandParser(
        rooms=[RoomRef("bedroom", ["Bedroom"]), RoomRef("kitchen", ["Kitchen"])],
        devices=[DeviceRef("bedroom_fan", "Ceiling Fan", "fan", "bedroom")],
    )
    cases = {
        "turn off everything": ("off", True, False, []),
        "close everything": ("off", True, False, []),
        "shut down everything": ("off", True, False, []),
        "turn on everything in this room": ("on", False, True, []),
        "switch everything off in the bedroom": ("off", False, False, ["bedroom"]),
        "turn on all the devices in here": ("on", False, True, []),
        "turn off all": ("off", True, False, []),
    }
    for text, (action, whole_home, this_room, rooms) in cases.items():
        [cmd] = p.parse(text)
        assert cmd.everything and cmd.action == action, text
        assert cmd.all_scope == whole_home and cmd.this_room == this_room and cmd.room_ids == rooms, text
    [lights] = p.parse("turn off all lights")
    assert not lights.everything and lights.device_types == ["light"]
