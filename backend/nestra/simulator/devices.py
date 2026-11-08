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


class Light(DeviceBase):
    type: Literal["light"] = "light"
    on: bool = False
    brightness: float = Field(80, ge=0, le=100)
    color_temp: int = Field(3000, ge=2200, le=6500, description="Kelvin")

    ADJUSTABLE: ClassVar[str] = "brightness"
    MIN_ON: ClassVar[float] = 5.0


class Fan(DeviceBase):
    type: Literal["fan"] = "fan"
    on: bool = False
    speed: float = Field(40, ge=0, le=100)

    ADJUSTABLE: ClassVar[str] = "speed"
    MIN_ON: ClassVar[float] = 10.0


class AirConditioner(DeviceBase):
    type: Literal["ac"] = "ac"
    on: bool = False
    setpoint: float = Field(24, ge=16, le=30)
    mode: Literal["cool", "heat", "auto"] = "cool"

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


Device = Annotated[
    Union[Light, Fan, AirConditioner, Blinds, Lock],
    Field(discriminator="type"),
]

DEVICE_CLASSES: dict[str, type[DeviceBase]] = {
    cls.model_fields["type"].default: cls for cls in (Light, Fan, AirConditioner, Blinds, Lock)
}
