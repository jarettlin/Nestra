"""Rule-based natural-language command parser.

It extracts *what* the user wants (device, room, action) and the *linguistic*
part of the request ("comfortable", "low", "a bit"). It deliberately does not
turn vague words into numbers: that is the fuzzy engine's job.

    "lower the fan to a comfortable speed"
      -> ParsedCommand(device_types=["fan"], action="decrease", term="comfortable")

The parser is offline and deterministic. To add an LLM later, make it return
the same ParsedCommand objects (for example as a fallback when this parser
finds nothing), and the rest of the pipeline stays unchanged.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from difflib import SequenceMatcher
from typing import Any

DEVICE_KEYWORDS: dict[str, list[str]] = {
    "fan": ["ceiling fan", "air circulator", "circulator", "fans", "fan"],
    "light": ["lights", "light", "lamps", "lamp", "lighting", "brightness", "bulbs", "bulb"],
    "ac": [
        "air conditioning", "air conditioner", "air con", "aircon", "ac",
        "thermostat", "temperature", "aircond",
    ],
    "blinds": ["window shades", "shades", "shade", "blinds", "blind", "curtains", "curtain"],
    "lock": ["front door", "door", "lock"],
}

# Words that imply a device when none is named ("make it brighter").
IMPLIED_TYPES: list[tuple[str, str]] = [
    (r"\b(brighter|brighten|darker|dimmer)\b", "light"),
    (r"\b(warmer|cooler|colder|hotter|degrees?)\b", "ac"),
    (r"\b(faster|slower)\b", "fan"),
    (r"\b(unlock|lock)\b", "lock"),
    (r"\b(open|close|shut)\b", "blinds"),
]

COMFORT_WORDS = r"comfortable|comfort|comfy|cozy|cosy|pleasant|nice|optimal|ideal|relaxing|auto|automatic"
LEVEL_WORDS = {
    "low": "low", "medium": "medium", "mid": "medium", "middle": "medium", "high": "high",
    "max": "max", "maximum": "max", "full": "max", "min": "min", "minimum": "min",
    "half": "half",
}
# Words that are a level only after "to/at/on" ("set it to dim"); otherwise
# they are verbs or directions ("dim the lights", "slow down").
AMBIGUOUS_LEVELS = {"dim": "dim", "bright": "bright", "slow": "slow", "fast": "fast"}

SMALL_HEDGES = r"a (?:little )?bit|a little|slightly|a tad|a touch|somewhat|just a bit"
LARGE_HEDGES = r"a lot|lots|much|way|significantly|a great deal|really"

INCREASE = (
    r"\b(increase|raise|turn (?:it |them )?up|up|higher|brighter|brighten|faster|"
    r"warmer|hotter|more|boost|speed up)\b"
)
DECREASE = (
    r"\b(decrease|lower|reduce|turn (?:it |them )?down|down|dim|dimmer|darker|"
    r"slower|cooler|colder|less|slow down)\b"
)
ALL_SCOPE = r"\b(all|every|everywhere|whole house|entire house)\b"
PRONOUN = r"\b(it|them|that|those)\b"
CLAUSE_SPLIT = re.compile(
    r"\s*(?:,\s*and then|,\s*then|\band then\b|\bthen\b|;|"
    r"\band\b(?=\s+(?:turn|switch|set|make|dim|open|close|shut|lock|unlock|lower|raise|"
    r"increase|decrease|reduce|brighten|put)\b))\s*"
)


@dataclass
class RoomRef:
    id: str
    names: list[str]


@dataclass
class DeviceRef:
    id: str
    name: str
    type: str
    room_id: str
    aliases: list[str] = field(default_factory=list)  # e.g. "television" for a TV


@dataclass
class ParsedCommand:
    text: str
    action: str | None  # on, off, set, increase, decrease, open, close, lock, unlock
    device_types: list[str] = field(default_factory=list)  # empty = decide from context
    device_ids: list[str] = field(default_factory=list)
    # Devices grouped by the phrase that matched them. A group with several
    # devices ("tv" matching two TVs) is ambiguous and may need a room.
    device_groups: list[list[str]] = field(default_factory=list)
    room_ids: list[str] = field(default_factory=list)
    all_scope: bool = False
    value: float | None = None  # absolute number: "set to 40%"
    delta: float | None = None  # relative number: "increase by 10"
    term: str | None = None  # linguistic target: "comfortable", "low", "dim", ...
    hedge: str | None = None  # "small" | "large" | None (moderate)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def normalize(text: str) -> str:
    text = text.lower()
    text = text.replace("°c", " degrees").replace("°", " degrees")
    text = re.sub(r"\ba/c\b|\bair-con\b", "ac", text)
    text = re.sub(r"[^\w\s%.,;'-]", " ", text)
    text = re.sub(r"(?<!\d)\.|\.(?!\d)", " ", text)  # drop full stops, keep decimals
    return " ".join(text.split())


def _phrase(p: str) -> re.Pattern[str]:
    return re.compile(rf"\b{re.escape(p)}\b")


class CommandParser:
    def __init__(self, rooms: list[RoomRef], devices: list[DeviceRef]) -> None:
        self.rooms = rooms
        self.devices = devices

    # ----------------------------------------------------------------- public
    def parse(self, text: str) -> list[ParsedCommand]:
        clean = normalize(text)
        commands: list[ParsedCommand] = []
        previous: ParsedCommand | None = None
        for clause in filter(None, CLAUSE_SPLIT.split(clean)):
            cmd = self._parse_clause(clause.strip(" ,"), previous)
            if cmd is not None:
                commands.append(cmd)
                previous = cmd
        return commands

    # --------------------------------------------------------------- matching
    def _match_devices(self, clause: str) -> list[tuple[DeviceRef, bool, str]]:
        """Match device names or aliases exactly, or names approximately to
        tolerate speech-to-text slips.

        Returns (device, exact, matched_phrase) triples.
        """
        words = clause.split()
        matched = []
        for device in self.devices:
            name = device.name.lower()
            exact = next(
                (p for p in (name, *device.aliases) if _phrase(p.lower()).search(clause)), None
            )
            if exact is not None:
                matched.append((device, True, exact.lower()))
                continue
            n = len(name.split())
            if n < 2:  # single words are too risky to fuzzy-match
                continue
            windows = (" ".join(words[i : i + n]) for i in range(len(words) - n + 1))
            if any(SequenceMatcher(None, w, name).ratio() >= 0.85 for w in windows):
                matched.append((device, False, name))
        return matched

    def _match_rooms(self, clause: str) -> list[str]:
        found = []
        for room in self.rooms:
            if any(_phrase(name.lower()).search(clause) for name in room.names):
                found.append(room.id)
        return found

    @staticmethod
    def _match_types(clause: str) -> list[str]:
        found: list[str] = []
        remaining = clause
        # Longest keywords first so "ceiling fan" wins over "fan" and is consumed once.
        keywords = sorted(
            ((kw, t) for t, kws in DEVICE_KEYWORDS.items() for kw in kws), key=lambda x: -len(x[0])
        )
        for kw, dtype in keywords:
            pattern = _phrase(kw)
            if pattern.search(remaining):
                remaining = pattern.sub(" ", remaining)
                if dtype not in found:
                    found.append(dtype)
        return found

    # ---------------------------------------------------------------- clauses
    def _parse_clause(self, clause: str, previous: ParsedCommand | None) -> ParsedCommand | None:
        matches = self._match_devices(clause)
        types = self._match_types(clause)
        if types:
            # "bedroom fan" must not fuzzy-match "Bedroom AC": keep devices of a
            # mentioned type, falling back to exact name matches only.
            kept = [m for m in matches if m[0].type in types] or [m for m in matches if m[1]]
        else:
            kept = matches
        # A phrase that is part of a longer matched phrase doesn't count on its own:
        # "reading lamp" shouldn't also pull in a device aliased "lamp".
        phrases = {p for _, _, p in kept}
        kept = [m for m in kept if not any(m[2] != p and _phrase(m[2]).search(p) for p in phrases)]
        devices = list({d.id: d for d, _, _ in kept}.values())
        groups: dict[str, list[str]] = {}
        for d, _, p in kept:
            groups.setdefault(p, []).append(d.id)
        if devices:
            types = list(dict.fromkeys(d.type for d in devices))
        rooms = self._match_rooms(clause)
        all_scope = bool(re.search(ALL_SCOPE, clause))

        value, delta = self._numbers(clause)
        term = self._term(clause)
        hedge = self._hedge(clause)
        if not types:
            types = [t for pattern, t in IMPLIED_TYPES if re.search(pattern, clause)][:1]
        if not types and value is not None and re.search(r"\bdegrees?\b", clause):
            types = ["ac"]

        # "...and set it to dim": inherit the target from the previous clause.
        device_ids = [d.id for d in devices]
        device_groups = list(groups.values())
        if not types and previous and (re.search(PRONOUN, clause) or not rooms):
            types = list(previous.device_types)
            device_ids = list(previous.device_ids)
            device_groups = [list(g) for g in previous.device_groups]
            rooms = rooms or list(previous.room_ids)

        action = self._action(clause, types, value, delta, term)
        if action is None and not types and term is None:
            return None
        return ParsedCommand(
            text=clause,
            action=action,
            device_types=types,
            device_ids=device_ids,
            device_groups=device_groups,
            room_ids=rooms,
            all_scope=all_scope,
            value=value,
            delta=delta,
            term=term,
            hedge=hedge,
        )

    @staticmethod
    def _numbers(clause: str) -> tuple[float | None, float | None]:
        by = re.search(r"\bby\s+(\d+(?:\.\d+)?)", clause)
        if by:
            return None, float(by.group(1))
        m = re.search(r"\b(\d+(?:\.\d+)?)\s*(%|percent|degrees?)?", clause)
        return (float(m.group(1)) if m else None), None

    @staticmethod
    def _term(clause: str) -> str | None:
        if re.search(rf"\b({COMFORT_WORDS})\b", clause):
            return "comfortable"
        for word, level in AMBIGUOUS_LEVELS.items():
            if re.search(rf"\b(to|at|on|be|is|more|too)\s+(a\s+)?{word}\b", clause):
                return level
        for word, level in LEVEL_WORDS.items():
            if re.search(rf"\b{word}\b", clause):
                return level
        return None

    @staticmethod
    def _hedge(clause: str) -> str | None:
        if re.search(rf"\b({SMALL_HEDGES})\b", clause):
            return "small"
        if re.search(rf"\b({LARGE_HEDGES})\b", clause):
            return "large"
        return None

    @staticmethod
    def _action(
        clause: str,
        types: list[str],
        value: float | None,
        delta: float | None,
        term: str | None,
    ) -> str | None:
        if re.search(r"\bunlock\b", clause):
            return "unlock"
        if re.search(r"\block\b", clause) and (not types or "lock" in types):
            return "lock"
        if not types or "blinds" in types:
            if re.search(r"\bopen\b", clause):
                return "open"
            if re.search(r"\b(close|shut)\b", clause) and not re.search(r"\bshut (?:it |them )?off\b", clause):
                return "close"

        increase = re.search(INCREASE, clause)
        decrease = re.search(DECREASE, clause)
        # A level word like "dim" after "to" is a target, not a direction.
        if decrease and term == "dim" and decrease.group(1) == "dim":
            decrease = None
        if increase and decrease:  # e.g. "turn up the cooler" - take the first one said
            if increase.start() < decrease.start():
                decrease = None
            else:
                increase = None
        if increase:
            return "increase"
        if decrease:
            return "decrease"
        if value is not None or term is not None or delta is not None:
            return "set"
        if re.search(r"\boff\b", clause):
            return "off"
        if re.search(r"\bon\b", clause):
            return "on"
        return None
