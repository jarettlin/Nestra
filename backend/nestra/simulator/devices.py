"""Simulated appliance models.

Each device type declares its main adjustable attribute (`ADJUSTABLE`), the
valid range for it, and the step it snaps to. The command processor uses these
to apply fuzzy outputs generically instead of special-casing every device.
"""

from __future__ import annotations

from typing import Annotated, ClassVar, Literal, Union

from pydantic import BaseModel, ConfigDict, Field


class DeviceBase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    room_id: str

    # Main continuous attribute and its range. None means on/off-style only.
    ADJUSTABLE: ClassVar[str | None] = None
    RANGE: ClassVar[tuple[float, float]] = (0.0, 100.0)
    STEP: ClassVar[float] = 1.0
    # Lowest value that still counts as "on" (used for "minimum").
    MIN_ON: ClassVar[float] = 1.0
    # Span used to size relative steps ("a bit higher"). Defaults to the full range.
    STEP_SPAN: ClassVar[float | None] = None
    UNIT: ClassVar[str] = "%"
    POWERED: ClassVar[bool] = True

    @classmethod
    def step_span(cls) -> float:
        lo, hi = cls.RANGE
        return cls.STEP_SPAN or (hi - lo)

    @classmethod
    def snap(cls, value: float) -> float:
        lo, hi = cls.RANGE
        snapped = round(value / cls.STEP) * cls.STEP
        return float(min(max(snapped, lo), hi))

    def level(self) -> float | None:
        return None if self.ADJUSTABLE is None else float(getattr(self, self.ADJUSTABLE))

    def format_level(self, value: float | None = None) -> str:
        value = self.level() if value is None else value
        if value is None:
            return ""
        text = f"{value:.1f}".rstrip("0").rstrip(".")
        return f"{text}{self.UNIT}"


class PoweredDevice(DeviceBase):
    """Something with a power switch, which can also switch itself on/off on a timer."""

    on: bool = False
    # Simulated-clock times (ISO 8601) when the device switches itself on/off. None = no timer.
    timer_on_at: str | None = None
    timer_off_at: str | None = None


class Light(PoweredDevice):
    type: Literal["light"] = "light"
    brightness: float = Field(80, ge=0, le=100)
    color_temp: int = Field(3000, ge=2200, le=6500, description="Kelvin")

    ADJUSTABLE: ClassVar[str] = "brightness"
    MIN_ON: ClassVar[float] = 5.0


class Fan(PoweredDevice):
    type: Literal["fan"] = "fan"
    speed: float = Field(40, ge=0, le=100)

    ADJUSTABLE: ClassVar[str] = "speed"
    MIN_ON: ClassVar[float] = 10.0


AC_MODES = ("cool", "dry", "fan", "heat", "auto")
AC_FAN_SPEEDS = ("auto", "low", "medium", "high")


class AirConditioner(PoweredDevice):
    type: Literal["ac"] = "ac"
    setpoint: float = Field(24, ge=16, le=30)
    # cool/heat: reach the setpoint. dry: dehumidify with gentle cooling.
    # fan: circulate air only. auto: cool or heat as needed.
    mode: Literal["cool", "dry", "fan", "heat", "auto"] = "cool"
    # How hard the indoor unit blows; auto runs high far from the setpoint, low near it.
    fan_speed: Literal["auto", "low", "medium", "high"] = "auto"

    ADJUSTABLE: ClassVar[str] = "setpoint"
    RANGE: ClassVar[tuple[float, float]] = (16.0, 30.0)
    STEP: ClassVar[float] = 0.5
    MIN_ON: ClassVar[float] = 16.0
    # People think about setpoints within roughly an 18-28°C band, so
    # "a bit warmer" should be ~1°C rather than a share of the full 14°C range.
    STEP_SPAN: ClassVar[float] = 10.0
    UNIT: ClassVar[str] = "°C"


class Blinds(DeviceBase):
    type: Literal["blinds"] = "blinds"
    position: float = Field(100, ge=0, le=100, description="Percent open")

    ADJUSTABLE: ClassVar[str] = "position"
    MIN_ON: ClassVar[float] = 0.0
    UNIT: ClassVar[str] = "% open"
    POWERED: ClassVar[bool] = False


class Lock(DeviceBase):
    type: Literal["lock"] = "lock"
    locked: bool = True

    POWERED: ClassVar[bool] = False


ApplianceKind = Literal[
    "tv", "kettle", "washer", "dryer", "fridge", "microwave", "coffee", "speaker",
    "heater", "purifier", "vacuum", "charger", "plug", "other",
]

# Labels for the UI and extra words people use for each kind ("turn off the television").
APPLIANCE_KINDS: dict[str, tuple[str, list[str]]] = {
    "tv": ("TV", ["tv", "television"]),
    "kettle": ("Kettle", ["kettle"]),
    "washer": ("Washing machine", ["washing machine", "washer"]),
    "dryer": ("Dryer", ["dryer", "tumble dryer"]),
    "fridge": ("Fridge", ["fridge", "refrigerator"]),
    "microwave": ("Microwave", ["microwave"]),
    "coffee": ("Coffee machine", ["coffee machine", "coffee maker"]),
    "speaker": ("Speaker", ["speaker", "speakers", "music"]),
    "heater": ("Heater", ["heater"]),
    "purifier": ("Air purifier", ["air purifier", "purifier"]),
    "vacuum": ("Robot vacuum", ["vacuum", "robot vacuum", "hoover"]),
    "charger": ("Charger", ["charger"]),
    "plug": ("Smart plug", ["plug", "socket", "outlet"]),
    "other": ("Other appliance", []),
}


class Appliance(PoweredDevice):
    """Any other electrical appliance that is simply switched on and off."""

    type: Literal["appliance"] = "appliance"
    kind: ApplianceKind = "other"

    def aliases(self) -> list[str]:
        return APPLIANCE_KINDS[self.kind][1]


Device = Annotated[
    Union[Light, Fan, AirConditioner, Blinds, Lock, Appliance],
    Field(discriminator="type"),
]

DEVICE_CLASSES: dict[str, type[DeviceBase]] = {
    cls.model_fields["type"].default: cls for cls in (Light, Fan, AirConditioner, Blinds, Lock, Appliance)
}

# Name used when the user doesn't give one (appliances use their kind's label).
DEFAULT_DEVICE_NAMES = {
    "light": "Light",
    "fan": "Fan",
    "ac": "Aircond",
    "blinds": "Blinds",
    "lock": "Door Lock",
    "appliance": "Appliance",
}


def default_device_name(device_type: str, kind: str | None = None) -> str:
    if device_type == "appliance" and kind and kind != "other":
        return APPLIANCE_KINDS.get(kind, ("Appliance", []))[0]
    return DEFAULT_DEVICE_NAMES.get(device_type, "Device")


DEVICE_TYPE_LABELS = {
    "light": "Light",
    "fan": "Fan",
    "ac": "Aircond",
    "blinds": "Blinds",
    "lock": "Door lock",
    "appliance": "Appliance",
}
