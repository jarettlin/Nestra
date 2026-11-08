"""The simulated home: rooms, their environment, devices, physics and activity log.

Everything that changes state goes through `Home`, which notifies subscribers
(the WebSocket hub) so the dashboard stays live without polling.
"""

from __future__ import annotations

import json
import math
from collections import deque
from dataclasses import asdict, dataclass
from itertools import count
from pathlib import Path
from typing import Any, Callable

from pydantic import BaseModel, Field, TypeAdapter

from .clock import SimClock
from .devices import AirConditioner, Blinds, Device, DeviceBase

DEFAULT_CONFIG = Path(__file__).resolve().parent.parent / "data" / "home.json"

# Physics constants, per simulated minute.
LEAK_RATE = 0.005  # share of the indoor/outdoor temperature gap closed per minute
AC_RATE = 0.10  # °C per minute an AC can move the room toward its setpoint
HUMIDITY_DRIFT = 0.003  # share of the indoor/outdoor humidity gap closed per minute
AC_DRYING = 0.2  # humidity points per minute removed while an AC is cooling
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


class ActivityEntry(BaseModel):
    id: int
    time: str
    title: str
    detail: str = ""
    source: str = "system"


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

    def log(self, title: str, detail: str = "", source: str = "system") -> ActivityEntry:
        entry = ActivityEntry(
            id=next(self._activity_ids),
            time=self.clock.now().isoformat(timespec="seconds"),
            title=title,
            detail=detail,
            source=source,
        )
        self.activity.appendleft(entry)
        self._emit("activity", entry.model_dump())
        return entry

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

    def tick(self, dt_minutes: float) -> None:
        """Advance room temperature/humidity/light by `dt_minutes` of simulated time."""
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
                if ac.mode in ("cool", "auto") and t > ac.setpoint:
                    t -= min(t - ac.setpoint, AC_RATE * dt_minutes)
                    if h > 40:
                        h -= min(h - 40, AC_DRYING * dt_minutes)
                elif ac.mode in ("heat", "auto") and t < ac.setpoint:
                    t += min(ac.setpoint - t, AC_RATE * dt_minutes)
            h += (h_out - h) * HUMIDITY_DRIFT * dt_minutes

            env.temperature = t
            env.humidity = min(max(h, 0.0), 100.0)
            after = (round(env.temperature, 1), round(env.humidity, 1), round(env.ambient_light, 1))
            if after != before:
                self._emit("environment", {"room_id": room.id, **self.room_snapshot(room.id)["environment"]})
