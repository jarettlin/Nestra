"""Linguistic variables and rule bases for Nestra.

Tune behaviour here: move membership breakpoints or add rules. Every rule base
is checked for coverage in the tests (some rule must fire for any input), so
you can experiment without silently breaking inference.

Systems:
  FAN_COMFORT    temperature, humidity        -> fan speed       ("comfortable fan")
  AC_COMFORT     temperature, humidity, time  -> AC setpoint     ("comfortable temperature")
  LIGHT_COMFORT  time of day, ambient light   -> brightness      ("cozy lighting")
  STEP_SIZE      intensity, headroom          -> step % of span  ("a bit lower", "much brighter")
"""

from __future__ import annotations

from .engine import FuzzyVariable, MamdaniSystem, rule, trapmf, trimf, union

# ---------------------------------------------------------------- inputs
TEMPERATURE = FuzzyVariable(
    "temperature",
    10,
    40,
    {
        "cold": trapmf(10, 10, 16, 20),
        "cool": trimf(17, 21, 24),
        "comfortable": trapmf(21, 23.5, 25.5, 28),
        "warm": trimf(25, 29, 33),
        "hot": trapmf(30, 34, 40, 40),
    },
)

HUMIDITY = FuzzyVariable(
    "humidity",
    0,
    100,
    {
        "dry": trapmf(0, 0, 25, 40),
        "normal": trapmf(30, 45, 55, 70),
        "humid": trapmf(60, 75, 100, 100),
    },
)

TIME_OF_DAY = FuzzyVariable(
    "time_of_day",
    0,
    24,
    {
        "night": union(trapmf(0, 0, 5, 6), trapmf(21, 23, 24, 24)),
        "morning": trapmf(5, 6, 9, 11),
        "day": trapmf(9, 11, 16, 18),
        "evening": trapmf(16, 18, 21, 23),
    },
)

AMBIENT_LIGHT = FuzzyVariable(
    "ambient_light",
    0,
    100,
    {
        "dark": trapmf(0, 0, 10, 30),
        "dim": trimf(15, 40, 65),
        "bright": trapmf(50, 75, 100, 100),
    },
)

# ---------------------------------------------------------------- outputs
# Term names double as words users can say: "set the fan to low".
FAN_SPEED = FuzzyVariable(
    "fan_speed",
    0,
    100,
    {
        "off": trapmf(0, 0, 2, 8),
        "low": trimf(5, 25, 45),
        "medium": trimf(35, 55, 75),
        "high": trimf(65, 80, 95),
        "max": trapmf(88, 96, 100, 100),
    },
)

BRIGHTNESS = FuzzyVariable(
    "brightness",
    0,
    100,
    {
        "off": trapmf(0, 0, 2, 6),
        "dim": trimf(4, 20, 36),
        "medium": trimf(30, 50, 70),
        "bright": trimf(60, 78, 92),
        "full": trapmf(85, 95, 100, 100),
    },
)

SETPOINT = FuzzyVariable(
    "setpoint",
    16,
    30,
    {
        "low": trapmf(16, 16, 19, 22),
        "cool": trimf(21, 22.5, 24),
        "medium": trimf(23, 24.5, 26),
        "high": trapmf(25.5, 26.5, 27, 28.5),
    },
)

BLINDS_POSITION = FuzzyVariable(
    "position",
    0,
    100,
    {
        "closed": trapmf(0, 0, 2, 10),
        "half": trimf(30, 50, 70),
        "open": trapmf(90, 98, 100, 100),
    },
)

# ---------------------------------------------------------------- comfort systems
FAN_COMFORT = MamdaniSystem(
    "fan_comfort",
    [TEMPERATURE, HUMIDITY],
    FAN_SPEED,
    [
        rule("temperature is cold", "off"),
        rule("temperature is cool and humidity is not humid", "off"),
        rule("temperature is cool and humidity is humid", "low"),
        rule("temperature is comfortable and humidity is not humid", "low"),
        rule("temperature is comfortable and humidity is humid", "medium"),
        rule("temperature is warm and humidity is dry", "medium"),
        rule("temperature is warm and humidity is normal", "medium"),
        rule("temperature is warm and humidity is humid", "high"),
        rule("temperature is hot", "high"),
        rule("temperature is very hot", "max"),
        rule("temperature is hot and humidity is humid", "max"),
    ],
)

AC_COMFORT = MamdaniSystem(
    "ac_comfort",
    [TEMPERATURE, HUMIDITY, TIME_OF_DAY],
    SETPOINT,
    [
        # Daytime baseline is around 24-25°C.
        rule("time_of_day is not night and humidity is not humid", "medium"),
        # Humid air feels warmer, so aim a little lower.
        rule("humidity is humid", "cool", weight=0.7),
        # A very hot room benefits from a lower target to pull down faster.
        rule("temperature is very hot", "low", weight=0.5),
        # People sleep better slightly warmer, and it saves energy.
        rule("time_of_day is night", "high", weight=0.8),
        rule("time_of_day is night and humidity is humid", "medium", weight=0.6),
    ],
)

LIGHT_COMFORT = MamdaniSystem(
    "light_comfort",
    [TIME_OF_DAY, AMBIENT_LIGHT],
    BRIGHTNESS,
    [
        rule("ambient_light is bright", "dim"),
        rule("ambient_light is dim and time_of_day is day", "medium"),
        rule("ambient_light is dark and time_of_day is day", "bright"),
        rule("ambient_light is dark and time_of_day is morning", "bright"),
        rule("ambient_light is dim and time_of_day is morning", "medium"),
        rule("ambient_light is not bright and time_of_day is evening", "medium"),
        rule("time_of_day is night", "dim"),
    ],
)

# ---------------------------------------------------------------- relative steps
# intensity: how strongly the user asked ("a bit" = 0.15, plain = 0.5, "a lot" = 0.85)
INTENSITY = FuzzyVariable(
    "intensity",
    0,
    1,
    {
        "small": trapmf(0, 0, 0.15, 0.4),
        "moderate": trimf(0.25, 0.5, 0.75),
        "large": trapmf(0.6, 0.85, 1, 1),
    },
)

# headroom: room left in the requested direction, as % of the device's span
HEADROOM = FuzzyVariable(
    "headroom",
    0,
    100,
    {
        "little": trapmf(0, 0, 5, 15),
        "some": trimf(10, 30, 50),
        "plenty": trapmf(40, 60, 100, 100),
    },
)

STEP = FuzzyVariable(
    "step",
    0,
    60,
    {
        "tiny": trimf(0, 5, 10),
        "small": trimf(7, 13, 20),
        "medium": trimf(15, 25, 35),
        "large": trapmf(30, 40, 60, 60),
    },
)

STEP_SIZE = MamdaniSystem(
    "step_size",
    [INTENSITY, HEADROOM],
    STEP,
    [
        rule("headroom is little", "tiny"),
        rule("intensity is small and headroom is not little", "small"),
        rule("intensity is moderate and headroom is not little", "medium"),
        rule("intensity is large and headroom is some", "medium"),
        rule("intensity is large and headroom is plenty", "large"),
    ],
)

HEDGE_INTENSITY = {"small": 0.15, None: 0.5, "large": 0.85}

# ---------------------------------------------------------------- lookups
COMFORT_SYSTEMS = {"fan": FAN_COMFORT, "ac": AC_COMFORT, "light": LIGHT_COMFORT}

LEVEL_VARIABLES = {
    "fan": FAN_SPEED,
    "light": BRIGHTNESS,
    "ac": SETPOINT,
    "blinds": BLINDS_POSITION,
}

# Words people use that map onto each device's own term names.
TERM_ALIASES = {
    "fan": {"dim": "low", "bright": "high", "slow": "low", "fast": "high", "half": "medium"},
    "light": {"low": "dim", "high": "bright", "half": "medium"},
    "ac": {"cold": "low", "warm": "high"},
    "blinds": {"medium": "half", "low": "closed", "high": "open"},
}

SYSTEMS = {s.name: s for s in (FAN_COMFORT, AC_COMFORT, LIGHT_COMFORT, STEP_SIZE)}
