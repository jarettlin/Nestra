"""Turn raw device changes into readable activity entries.

    speed 85 -> 55   becomes   Fan speed: High (85%) -> Medium (55%)

Numbers are labelled with the fuzzy term they best match, so the history uses
the same words people say in commands.
"""

from __future__ import annotations

from typing import Any

from .fuzzy.rules import LEVEL_VARIABLES
from .simulator import Change, Home
from .simulator.home import ActivityChange, ActivityEntry

ATTRIBUTE_LABELS = {
    "on": "Power",
    "brightness": "Brightness",
    "speed": "Fan speed",
    "setpoint": "Temperature",
    "mode": "Mode",
    "position": "Blinds",
    "locked": "Lock",
    "color_temp": "Colour",
    "kind": "Appliance type",
    "fan_speed": "Fan speed",
    "timer_on_at": "On timer",
    "timer_off_at": "Off timer",
    "name": "Name",
    "room_id": "Room",
}

_LEVEL_ATTRIBUTES = {"brightness": "light", "speed": "fan"}


def format_value(home: Home, attribute: str, value: Any) -> str:
    if attribute.startswith("timer_"):
        return "Not set" if not value else str(value)[11:16]
    if attribute == "on":
        return "On" if value else "Off"
    if attribute == "locked":
        return "Locked" if value else "Unlocked"
    if attribute == "room_id":
        room = home.rooms.get(value)
        return room.name if room else str(value)
    if attribute == "setpoint":
        return f"{float(value):g}°C"
    if attribute == "position":
        v = float(value)
        return "Closed" if v <= 0 else "Open" if v >= 100 else f"{v:.0f}% open"
    if attribute == "color_temp":
        return f"{value}K"
    if attribute in _LEVEL_ATTRIBUTES:
        variable = LEVEL_VARIABLES[_LEVEL_ATTRIBUTES[attribute]]
        term = variable.best_term(float(value)).capitalize()
        return f"{term} ({float(value):.0f}%)"
    if isinstance(value, str):
        return value.replace("_", " ").capitalize()
    return str(value)


def describe(home: Home, change: Change) -> ActivityChange:
    return ActivityChange(
        attribute=change.attribute,
        label=ATTRIBUTE_LABELS.get(change.attribute, change.attribute.replace("_", " ").capitalize()),
        old=change.old,
        new=change.new,
        old_text=format_value(home, change.attribute, change.old),
        new_text=format_value(home, change.attribute, change.new),
    )


def record(
    home: Home,
    device_id: str,
    changes: list[Change],
    *,
    source: str,
    command: str | None = None,
) -> ActivityEntry | None:
    """Log one activity entry for a device's changes (nothing if nothing changed)."""
    if not changes:
        return None
    device = home.devices.get(device_id)
    described = [describe(home, c) for c in changes]
    # Show the interesting change first: "Fan speed" before "Power".
    described.sort(key=lambda c: c.attribute == "on")
    name = device.name if device else changes[0].device_name
    room_id = device.room_id if device else changes[0].room_id
    return home.log(
        name,
        source=source,
        device_id=device_id,
        device_type=device.type if device else None,
        room_id=room_id,
        changes=described,
        command=command,
    )
