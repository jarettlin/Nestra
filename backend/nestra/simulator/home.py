"""The simulated home: rooms, their environment, devices, physics and activity log.

Everything that changes state goes through `Home`, which notifies subscribers
(the WebSocket hub) so the dashboard stays live without polling.
"""

from __future__ import annotations

import json
import math
import re
from collections import deque
from dataclasses import asdict, dataclass
from itertools import count
from pathlib import Path
from typing import Any, Callable

from pydantic import BaseModel, Field, TypeAdapter

from .clock import SimClock
from .devices import AirConditioner, Blinds, Device, DeviceBase, PoweredDevice, default_device_name

DEFAULT_CONFIG = Path(__file__).resolve().parent.parent / "data" / "home.json"

# Physics constants, per simulated minute.
LEAK_RATE = 0.005  # share of the indoor/outdoor temperature gap closed per minute
AC_RATE = 0.10  # °C per minute an AC can move the room toward its setpoint
HUMIDITY_DRIFT = 0.003  # share of the indoor/outdoor humidity gap closed per minute
AC_DRYING = 0.2  # humidity points per minute removed while an AC is cooling
DRY_MODE_DRYING = 0.5  # humidity points per minute in dry (dehumidify) mode
DRY_MODE_COOLING = 0.3  # dry mode cools gently, at this share of AC_RATE
# Cooling/heating power by indoor fan speed. "auto" is decided per tick.
FAN_SPEED_POWER = {"low": 0.6, "medium": 1.0, "high": 1.4}
NO_BLINDS_OPENNESS = 0.6  # rooms without blinds still let some daylight in

_IMMUTABLE_FIELDS = {"id", "type", "name", "room_id"}


class Environment(BaseModel):
    temperature: float = Field(description="°C")
    humidity: float = Field(ge=0, le=100, description="Relative humidity %")
    ambient_light: float = Field(0.0, ge=0, le=100, description="Natural light level 0-100")
    occupied: bool = True


class Room(BaseModel):
    id: str
    name: str
    aliases: list[str] = []
    environment: Environment


class Weather(BaseModel):
    mean_temperature: float = 28.0
    amplitude: float = 4.0
    humidity: float = 70.0


class HomeConfig(BaseModel):
    name: str
    weather: Weather = Weather()
    rooms: list[Room]
    devices: list[Device]


class ActivityChange(BaseModel):
    attribute: str
    label: str  # "Fan speed"
    old: Any = None
    new: Any = None
    old_text: str = ""  # "High (85%)"
    new_text: str = ""


class ActivityEntry(BaseModel):
    id: int
    time: str
    title: str
    detail: str = ""
    source: str = "system"  # voice | manual | system | cli
    device_id: str | None = None
    device_type: str | None = None
    room_id: str | None = None
    room_name: str | None = None
    changes: list[ActivityChange] = []
    command: str | None = None  # the spoken/typed command, for voice entries


@dataclass(frozen=True)
class Change:
    device_id: str
    device_name: str
    room_id: str
    attribute: str
    old: Any
    new: Any

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


Listener = Callable[[dict[str, Any]], None]
_device_adapter: TypeAdapter[Device] = TypeAdapter(Device)


class Home:
    def __init__(self, config: HomeConfig, clock: SimClock | None = None) -> None:
        self.name = config.name
        self.weather = config.weather
        self.clock = clock or SimClock()
        self.rooms: dict[str, Room] = {r.id: r for r in config.rooms}
        self.devices: dict[str, DeviceBase] = {}
        for device in config.devices:
            if device.room_id not in self.rooms:
                raise ValueError(f"Device {device.id!r} references unknown room {device.room_id!r}")
            if device.id in self.devices:
                raise ValueError(f"Duplicate device id {device.id!r}")
            self.devices[device.id] = device
        self.activity: deque[ActivityEntry] = deque(maxlen=200)
        self._activity_ids = count(1)
        self._listeners: list[Listener] = []
        # Bumped whenever rooms/devices are added, removed or renamed, so the
        # command parser knows to rebuild its vocabulary.
        self.structure_version = 0
        self._update_ambient_light()

    @classmethod
    def from_file(cls, path: Path | str = DEFAULT_CONFIG, clock: SimClock | None = None) -> Home:
        data = json.loads(Path(path).read_text())
        return cls(HomeConfig.model_validate(data), clock=clock)

    # ----------------------------------------------------------------- events
    def subscribe(self, listener: Listener) -> None:
        self._listeners.append(listener)

    def _emit(self, event_type: str, data: Any) -> None:
        message = {"type": event_type, "data": data}
        for listener in list(self._listeners):
            listener(message)

    def log(self, title: str, detail: str = "", source: str = "system", **fields: Any) -> ActivityEntry:
        room_id = fields.get("room_id")
        if room_id and "room_name" not in fields and room_id in self.rooms:
            fields["room_name"] = self.rooms[room_id].name
        entry = ActivityEntry(
            id=next(self._activity_ids),
            time=self.clock.now().isoformat(timespec="seconds"),
            title=title,
            detail=detail,
            source=source,
            **fields,
        )
        self.activity.appendleft(entry)
        self._emit("activity", entry.model_dump())
        return entry

    def restore_activity(self, entries: list[ActivityEntry]) -> None:
        """Load saved history (newest first) and continue numbering after it."""
        ordered = sorted(entries, key=lambda e: e.id, reverse=True)
        self.activity = deque(ordered[: self.activity.maxlen], maxlen=self.activity.maxlen)
        self._activity_ids = count(max((e.id for e in entries), default=0) + 1)

    # ------------------------------------------------------------------ state
    def devices_in(self, room_id: str) -> list[DeviceBase]:
        return [d for d in self.devices.values() if d.room_id == room_id]

    def outside_temperature(self) -> float:
        # Coolest around 03:00, warmest around 15:00.
        hour = self.clock.hour()
        return self.weather.mean_temperature + self.weather.amplitude * math.sin(
            2 * math.pi * (hour - 9) / 24
        )

    def room_snapshot(self, room_id: str) -> dict[str, Any]:
        room = self.rooms[room_id]
        env = room.environment
        return {
            "id": room.id,
            "name": room.name,
            "environment": {
                "temperature": round(env.temperature, 1),
                "humidity": round(env.humidity, 1),
                "ambient_light": round(env.ambient_light, 1),
                "occupied": env.occupied,
            },
            "devices": [d.model_dump() for d in self.devices_in(room_id)],
        }

    def snapshot(self, activity_limit: int = 20) -> dict[str, Any]:
        return {
            "name": self.name,
            "time": self.clock.now().isoformat(timespec="seconds"),
            "outside": {
                "temperature": round(self.outside_temperature(), 1),
                "humidity": round(self.weather.humidity, 1),
            },
            "rooms": [self.room_snapshot(rid) for rid in self.rooms],
            "activity": [a.model_dump() for a in list(self.activity)[:activity_limit]],
        }

    def update_device(
        self, device_id: str, updates: dict[str, Any], *, source: str = "manual"
    ) -> list[Change]:
        """Validate and apply attribute updates. Raises KeyError / ValueError on bad input."""
        device = self.devices[device_id]
        forbidden = _IMMUTABLE_FIELDS & updates.keys()
        if forbidden:
            raise ValueError(f"Cannot change {sorted(forbidden)} on a device")
        # Re-validating the whole model enforces ranges and rejects unknown fields.
        updated = _device_adapter.validate_python({**device.model_dump(), **updates})
        changes = [
            Change(device.id, device.name, device.room_id, key, getattr(device, key), getattr(updated, key))
            for key in updates
            if getattr(device, key) != getattr(updated, key)
        ]
        if not changes:
            return []
        self.devices[device_id] = updated
        self._emit("device", {**updated.model_dump(), "source": source})
        if isinstance(updated, Blinds):
            self._update_ambient_light()
        return changes

    # -------------------------------------------------------------- structure
    def to_config(self) -> HomeConfig:
        """Current home as a config (what gets saved)."""
        return HomeConfig(
            name=self.name,
            weather=self.weather,
            rooms=[r.model_copy(deep=True) for r in self.rooms.values()],
            devices=list(self.devices.values()),
        )

    def _structure_changed(self) -> None:
        self.structure_version += 1
        self._emit("snapshot", self.snapshot())

    def _unique_id(self, name: str, taken: dict[str, Any]) -> str:
        base = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_") or "item"
        candidate, n = base, 2
        while candidate in taken:
            candidate, n = f"{base}_{n}", n + 1
        return candidate

    @staticmethod
    def _clean_name(name: str) -> str:
        cleaned = " ".join(name.split())
        if not cleaned:
            raise ValueError("Name can't be empty")
        if len(cleaned) > 40:
            raise ValueError("Name must be 40 characters or fewer")
        return cleaned

    def _check_room_name(self, name: str, exclude: str | None = None) -> None:
        for room in self.rooms.values():
            if room.id != exclude and room.name.lower() == name.lower():
                raise ValueError(f"There is already a room called {room.name!r}")

    def _check_device_name(self, name: str, room_id: str, exclude: str | None = None) -> None:
        for d in self.devices_in(room_id):
            if d.id != exclude and d.name.lower() == name.lower():
                raise ValueError(f"{self.rooms[room_id].name} already has a device called {d.name!r}")

    def add_room(self, name: str, *, source: str = "manual") -> Room:
        name = self._clean_name(name)
        self._check_room_name(name)
        room = Room(
            id=self._unique_id(name, self.rooms),
            name=name,
            environment=Environment(
                temperature=self.outside_temperature(), humidity=self.weather.humidity
            ),
        )
        self.rooms[room.id] = room
        self._update_ambient_light()
        self.log(f"Added room {name}", source=source, room_id=room.id)
        self._structure_changed()
        return room

    def rename_room(self, room_id: str, name: str, *, source: str = "manual") -> Room:
        room = self.rooms[room_id]
        name = self._clean_name(name)
        if name == room.name:
            return room
        self._check_room_name(name, exclude=room_id)
        old = room.name
        room.name = name
        self.log(f"Renamed room {old} to {name}", source=source, room_id=room_id)
        self._structure_changed()
        return room

    def remove_room(self, room_id: str, *, source: str = "manual") -> list[str]:
        """Remove a room and every device in it. Returns the removed device ids."""
        room = self.rooms[room_id]
        if len(self.rooms) == 1:
            raise ValueError("A home needs at least one room")
        removed = [d.id for d in self.devices_in(room_id)]
        for device_id in removed:
            del self.devices[device_id]
        del self.rooms[room_id]
        count_text = f" and {len(removed)} device{'s' if len(removed) != 1 else ''}" if removed else ""
        self.log(f"Removed room {room.name}{count_text}", source=source)
        self._structure_changed()
        return removed

    def default_name(self, device_type: str, room_id: str, kind: str | None = None) -> str:
        """"Aircond", or "Aircond 2" if the room already has one with that name."""
        base = default_device_name(device_type, kind)
        taken = {d.name.lower() for d in self.devices_in(room_id)}
        name, n = base, 2
        while name.lower() in taken:
            name, n = f"{base} {n}", n + 1
        return name

    def add_device(
        self, device_type: str, name: str | None, room_id: str, *, source: str = "manual", **attributes: Any
    ) -> DeviceBase:
        """Add a device. A blank name becomes a default like "Aircond" or "TV"."""
        if room_id not in self.rooms:
            raise KeyError(room_id)
        if not (name or "").strip():
            name = self.default_name(device_type, room_id, attributes.get("kind"))
        name = self._clean_name(name)
        self._check_device_name(name, room_id)
        forbidden = _IMMUTABLE_FIELDS & attributes.keys()
        if forbidden:
            raise ValueError(f"Cannot set {sorted(forbidden)} as attributes")
        device = _device_adapter.validate_python(
            {
                "id": self._unique_id(f"{room_id}_{name}", self.devices),
                "type": device_type,
                "name": name,
                "room_id": room_id,
                **attributes,
            }
        )
        self.devices[device.id] = device
        self.log(f"Added {name}", source=source, device_id=device.id, device_type=device.type, room_id=room_id)
        self._structure_changed()
        return device

    def edit_device(
        self, device_id: str, *, name: str | None = None, room_id: str | None = None, source: str = "manual"
    ) -> list[Change]:
        """Rename a device or move it to another room."""
        device = self.devices[device_id]
        new_name = self._clean_name(name) if name is not None else device.name
        new_room = room_id if room_id is not None else device.room_id
        if new_room not in self.rooms:
            raise KeyError(new_room)
        self._check_device_name(new_name, new_room, exclude=device_id)
        changes = [
            Change(device.id, device.name, device.room_id, attr, old, new)
            for attr, old, new in (("name", device.name, new_name), ("room_id", device.room_id, new_room))
            if old != new
        ]
        if not changes:
            return []
        self.devices[device_id] = device.model_copy(update={"name": new_name, "room_id": new_room})
        self._structure_changed()
        return changes

    def remove_device(self, device_id: str, *, source: str = "manual") -> None:
        device = self.devices.pop(device_id)
        self.log(f"Removed {device.name}", source=source, device_type=device.type, room_id=device.room_id)
        self._structure_changed()

    # ---------------------------------------------------------------- physics
    def _daylight(self) -> float:
        hour = self.clock.hour()
        return max(0.0, math.sin(math.pi * (hour - 6) / 12)) * 100

    def _update_ambient_light(self) -> None:
        daylight = self._daylight()
        for room in self.rooms.values():
            blinds = [d for d in self.devices_in(room.id) if isinstance(d, Blinds)]
            openness = (
                sum(b.position for b in blinds) / (100 * len(blinds)) if blinds else NO_BLINDS_OPENNESS
            )
            room.environment.ambient_light = daylight * openness

    def run_timers(self) -> list[str]:
        """Switch devices whose on/off timer is due. Returns the ids that changed."""
        now = self.clock.now().isoformat(timespec="seconds")
        fired = []
        for device in list(self.devices.values()):
            if not isinstance(device, PoweredDevice):
                continue
            for field_name, turn_on in (("timer_off_at", False), ("timer_on_at", True)):
                due = getattr(device, field_name)
                if due is None or due > now:
                    continue
                current = self.devices[device.id]
                changes = self.update_device(device.id, {field_name: None, "on": turn_on}, source="timer")
                power = [c for c in changes if c.attribute == "on"]
                fired.append(device.id)
                if not power:  # already in that state; the timer just clears
                    continue
                self.log(
                    current.name,
                    source="timer",
                    device_id=device.id,
                    device_type=device.type,
                    room_id=device.room_id,
                    changes=[
                        ActivityChange(
                            attribute="on", label="Power",
                            old=c.old, new=c.new, old_text="On" if c.old else "Off", new_text="On" if c.new else "Off",
                        )
                        for c in power
                    ],
                    detail="Timer",
                )
        return fired

    def tick(self, dt_minutes: float) -> None:
        """Advance room temperature/humidity/light by `dt_minutes` of simulated time."""
        self.run_timers()
        t_out = self.outside_temperature()
        h_out = self.weather.humidity
        self._update_ambient_light()
        for room in self.rooms.values():
            env = room.environment
            before = (round(env.temperature, 1), round(env.humidity, 1), round(env.ambient_light, 1))
            t, h = env.temperature, env.humidity

            t += (t_out - t) * LEAK_RATE * dt_minutes
            for ac in self.devices_in(room.id):
                if not (isinstance(ac, AirConditioner) and ac.on):
                    continue
                gap = t - ac.setpoint
                power = FAN_SPEED_POWER.get(ac.fan_speed) or (1.4 if abs(gap) > 2 else 0.8)
                rate = AC_RATE * power * dt_minutes
                if ac.mode == "dry":
                    if h > 40:
                        h -= min(h - 40, DRY_MODE_DRYING * dt_minutes)
                    if gap > 0:
                        t -= min(gap, rate * DRY_MODE_COOLING)
                elif ac.mode in ("cool", "auto") and gap > 0:
                    t -= min(gap, rate)
                    if h > 40:
                        h -= min(h - 40, AC_DRYING * dt_minutes)
                elif ac.mode in ("heat", "auto") and gap < 0:
                    t += min(-gap, rate)
                # "fan" mode only moves air: no temperature change.
            h += (h_out - h) * HUMIDITY_DRIFT * dt_minutes

            env.temperature = t
            env.humidity = min(max(h, 0.0), 100.0)
            after = (round(env.temperature, 1), round(env.humidity, 1), round(env.ambient_light, 1))
            if after != before:
                self._emit("environment", {"room_id": room.id, **self.room_snapshot(room.id)["environment"]})
