"""Command pipeline: text -> parsed intent -> fuzzy values -> simulator changes.

    CommandProcessor(home).execute("lower the fan to a comfortable speed", room_context="living_room")

Resolution order for "which device?":
  named device > named room > "all" > the tablet's room (room_context) > the only one in the home
and if it is still ambiguous, the result asks the user to clarify instead of guessing.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from .fuzzy.engine import InferenceResult
from .fuzzy.rules import (
    COMFORT_SYSTEMS,
    HEDGE_INTENSITY,
    LEVEL_VARIABLES,
    STEP_SIZE,
    TERM_ALIASES,
)
from . import activity
from .nlu import CommandParser, DeviceRef, ParsedCommand, RoomRef
from .simulator import Appliance, Blinds, Change, Home, Lock
from .simulator.devices import AirConditioner, DeviceBase, PoweredDevice

COMFORT_TYPES = ("light", "fan", "ac")
TYPE_NOUNS = {
    "light": "light", "fan": "fan", "ac": "AC", "blinds": "blinds", "lock": "lock", "appliance": "appliance",
}


@dataclass
class Plan:
    device: DeviceBase
    updates: dict[str, Any]
    reply: str
    explanation: dict[str, Any] | None = None


@dataclass
class CommandResult:
    ok: bool
    reply: str
    changes: list[Change] = field(default_factory=list)
    explanations: list[dict[str, Any]] = field(default_factory=list)
    parsed: list[ParsedCommand] = field(default_factory=list)
    needs_clarification: bool = False
    needs_confirmation: bool = False
    options: list[dict[str, str]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "reply": self.reply,
            "changes": [c.to_dict() for c in self.changes],
            "explanations": self.explanations,
            "parsed": [p.to_dict() for p in self.parsed],
            "needs_clarification": self.needs_clarification,
            "needs_confirmation": self.needs_confirmation,
            "options": self.options,
        }


class Clarify(Exception):
    def __init__(self, question: str, options: list[dict[str, str]] | None = None) -> None:
        super().__init__(question)
        self.question = question
        self.options = options or []


class CommandProcessor:
    def __init__(self, home: Home) -> None:
        self.home = home
        self._parser: CommandParser | None = None
        self._parser_version = -1

    @property
    def parser(self) -> CommandParser:
        """Vocabulary comes from the home's rooms and devices; rebuilt when they change."""
        if self._parser is None or self._parser_version != self.home.structure_version:
            home = self.home
            self._parser = CommandParser(
                rooms=[RoomRef(r.id, [r.name, *r.aliases]) for r in home.rooms.values()],
                devices=[
                    DeviceRef(
                        d.id, d.name, d.type, d.room_id,
                        aliases=d.aliases() if isinstance(d, Appliance) else [],
                    )
                    for d in home.devices.values()
                ],
            )
            self._parser_version = home.structure_version
        return self._parser

    # ------------------------------------------------------------------ entry
    def execute(
        self,
        text: str,
        *,
        room_context: str | None = None,
        confirm: bool = False,
        source: str = "voice",
    ) -> CommandResult:
        parsed = self.parser.parse(text)
        if not parsed:
            return CommandResult(
                False,
                "Sorry, I couldn't tell what to control. Try \"turn on the living room lights\".",
            )

        # Plan everything first so a clarification never leaves a half-applied command.
        plans: list[Plan] = []
        notes: list[str] = []
        try:
            for cmd in parsed:
                if cmd.action is None:
                    raise Clarify(f"What should I do with the {self._noun(cmd)}?")
                if cmd.everything and cmd.action in ("on", "off"):
                    summary = self._plan_everything(cmd, room_context)
                    if isinstance(summary, str):
                        notes.append(summary)
                    else:
                        plans += summary
                    continue
                for device in self._resolve(cmd, room_context):
                    plan_or_note = self._plan(cmd, device, confirm)
                    if isinstance(plan_or_note, Plan):
                        plan_or_note.reply = self._with_room(device, plan_or_note.reply)
                        plans.append(plan_or_note)
                    else:
                        notes.append(self._with_room(device, plan_or_note))
        except Clarify as q:
            return CommandResult(
                False, q.question, parsed=parsed, needs_clarification=True, options=q.options
            )
        except NeedsConfirmation as c:
            return CommandResult(False, str(c), parsed=parsed, needs_confirmation=True)

        changes: list[Change] = []
        replies: list[str] = []
        explanations: list[dict[str, Any]] = []
        for plan in plans:
            applied = self.home.update_device(plan.device.id, plan.updates, source=source)
            changes += applied
            if plan.reply:
                replies.append(plan.reply)
            if plan.explanation:
                explanations.append(plan.explanation)
            activity.record(self.home, plan.device.id, applied, source=source, command=text)
        replies += notes
        reply = " ".join(_sentence(r) for r in replies) or "Nothing to change."
        return CommandResult(True, reply, changes, explanations, parsed)

    def _plan_everything(self, cmd: ParsedCommand, room_context: str | None) -> list[Plan] | str:
        """'Turn off everything (in here)': switch whatever isn't already, with one summary reply."""
        on = cmd.action == "on"
        devices = [d for d in self._resolve(cmd, room_context) if isinstance(d, PoweredDevice)]
        room_ids = list(dict.fromkeys(d.room_id for d in devices))
        if cmd.all_scope or len(room_ids) > 1:
            where = "across the home"
        else:
            where = f"in the {self.home.rooms[room_ids[0]].name}" if room_ids else ""
        todo = [d for d in devices if d.on != on]
        if not todo:
            return f"Everything {where} is already {cmd.action}".replace("  ", " ")
        plans = [Plan(d, {"on": on}, "") for d in todo]
        if len(todo) == 1:
            plans[0].reply = self._with_room(todo[0], f"{todo[0].name} turned {cmd.action}")
        else:
            plans[0].reply = f"Turned {cmd.action} {len(todo)} devices {where}".strip()
        return plans

    def _with_room(self, device: DeviceBase, text: str) -> str:
        """'Aircond turned on' -> 'Bedroom Aircond turned on' when another room has an 'Aircond' too."""
        room = self.home.rooms.get(device.room_id)
        same_name = any(
            d.id != device.id and d.name.lower() == device.name.lower() for d in self.home.devices.values()
        )
        if not room or not same_name or room.name.lower() in text.lower():
            return text
        return text.replace(device.name, f"{room.name} {device.name}", 1)

    # ------------------------------------------------------------- resolution
    @staticmethod
    def _noun(cmd: ParsedCommand) -> str:
        return TYPE_NOUNS.get(cmd.device_types[0], "device") if cmd.device_types else "device"

    def _resolve(self, cmd: ParsedCommand, room_context: str | None) -> list[DeviceBase]:
        if cmd.device_ids:
            return self._resolve_named(cmd, room_context)

        types = cmd.device_types or (list(COMFORT_TYPES) if cmd.term == "comfortable" else [])
        if not types:
            raise Clarify("Which device do you mean?")
        pool = [d for d in self.home.devices.values() if d.type in types]

        if cmd.room_ids:
            pool = [d for d in pool if d.room_id in cmd.room_ids]
        elif cmd.this_room and room_context:
            pool = [d for d in pool if d.room_id == room_context]
        elif not cmd.all_scope:
            here = [d for d in pool if d.room_id == room_context]
            if here:
                pool = here
            else:
                rooms = list(dict.fromkeys(d.room_id for d in pool))
                if len(rooms) > 1:
                    names = [self.home.rooms[r].name for r in rooms]
                    raise Clarify(
                        f"Which {self._noun(cmd)}? I found one in {_join(names)}.",
                        [{"room_id": r, "room_name": self.home.rooms[r].name} for r in rooms],
                    )

        if not pool:
            room_ids = cmd.room_ids or ([room_context] if cmd.this_room and room_context else [])
            where = " and ".join(self.home.rooms[r].name for r in room_ids if r in self.home.rooms) or "the home"
            if cmd.everything:
                raise Clarify(f"There's nothing to switch in {where}.")
            raise Clarify(f"I couldn't find a {self._noun(cmd)} in {where}.")
        return pool

    def _resolve_named(self, cmd: ParsedCommand, room_context: str | None) -> list[DeviceBase]:
        """Devices named directly. If one phrase matched devices in several rooms
        ("the TV" with a TV in two rooms), narrow by room or ask which."""
        groups = cmd.device_groups or [[i] for i in cmd.device_ids]
        result: list[DeviceBase] = []
        for group in groups:
            devices = [self.home.devices[i] for i in group if i in self.home.devices]
            rooms = list(dict.fromkeys(d.room_id for d in devices))
            if len(rooms) > 1 and not cmd.all_scope:
                if cmd.room_ids:
                    devices = [d for d in devices if d.room_id in cmd.room_ids] or devices
                elif any(d.room_id == room_context for d in devices):
                    devices = [d for d in devices if d.room_id == room_context]
                else:
                    names = [self.home.rooms[r].name for r in rooms]
                    raise Clarify(
                        f"Which {devices[0].name}? I found one in {_join(names)}.",
                        [{"room_id": r, "room_name": self.home.rooms[r].name} for r in rooms],
                    )
            result += [d for d in devices if d not in result]
        return result

    # --------------------------------------------------------------- planning
    def _plan(self, cmd: ParsedCommand, device: DeviceBase, confirm: bool) -> Plan | str:
        if cmd.action == "timer":
            return self._plan_timer(cmd, device)
        if cmd.attribute in ("fan_speed", "mode") and cmd.action != "off":
            result = self._plan_ac_setting(cmd, device)
        else:
            result = self._plan_basic(cmd, device, confirm)
        if not isinstance(result, Plan):
            return result
        if cmd.timer_action in ("on", "off"):
            # "turn on the fan for 30 minutes": do it now and schedule the opposite.
            timer = self._plan_timer(cmd, device)
            if isinstance(timer, Plan):
                result.updates.update(timer.updates)
                result.reply += f"; {timer.reply[len(device.name) + 1:]}"
        elif cmd.timer_action == "unsupported":
            result.reply += " now (timers can only switch devices on or off)"
        return result

    # ------------------------------------------------------------------ timers
    def _due(self, cmd: ParsedCommand) -> tuple[str, str]:
        return timer_due(self.home.clock.now(), minutes=cmd.timer_minutes, at=cmd.timer_at)

    def _plan_timer(self, cmd: ParsedCommand, device: DeviceBase) -> Plan | str:
        if not isinstance(device, PoweredDevice):
            return f"The {device.name} doesn't have a timer"
        if cmd.timer_action == "cancel":
            if device.timer_on_at is None and device.timer_off_at is None:
                return f"The {device.name} has no timer set"
            return Plan(device, {"timer_on_at": None, "timer_off_at": None}, f"{device.name} timer cancelled")
        due, when = self._due(cmd)
        return Plan(device, {f"timer_{cmd.timer_action}_at": due}, f"{device.name} will turn {cmd.timer_action} at {when}")

    # --------------------------------------------------------- aircond settings
    def _plan_ac_setting(self, cmd: ParsedCommand, device: DeviceBase) -> Plan | str:
        name = device.name
        if not isinstance(device, AirConditioner):
            what = "fan speed setting" if cmd.attribute == "fan_speed" else "modes"
            return f"The {name} doesn't have {what}"
        if cmd.attribute == "mode":
            if not cmd.setting:
                return f"Which mode for the {name}? Cool, dry, fan, heat or auto"
            return Plan(device, {"mode": cmd.setting, "on": True}, f"{name} set to {cmd.setting} mode")
        levels = ["low", "medium", "high"]
        if cmd.setting:
            new = cmd.setting
        elif cmd.action in ("increase", "decrease"):
            current = device.fan_speed if device.fan_speed != "auto" else "medium"
            step = 1 if cmd.action == "increase" else -1
            new = levels[min(max(levels.index(current) + step, 0), len(levels) - 1)]
        else:
            return f"What fan speed for the {name}? Auto, low, medium or high"
        return Plan(device, {"fan_speed": new, "on": True}, f"{name} fan set to {new}")

    def _plan_basic(self, cmd: ParsedCommand, device: DeviceBase, confirm: bool) -> Plan | str:
        action = cmd.action
        name = device.name

        if isinstance(device, Lock):
            if action == "unlock":
                if not confirm:
                    raise NeedsConfirmation(f"Unlocking the {name} needs confirmation. Should I go ahead?")
                return Plan(device, {"locked": False}, f"{name} unlocked")
            if action == "lock":
                return Plan(device, {"locked": True}, f"{name} locked")
            return f"I can only lock or unlock the {name}"

        if isinstance(device, Blinds):
            if action in ("open", "on") and cmd.hedge is None and cmd.term is None and cmd.value is None:
                return Plan(device, {"position": 100.0}, f"{name} opened")
            if action in ("close", "off") and cmd.hedge is None and cmd.term is None and cmd.value is None:
                return Plan(device, {"position": 0.0}, f"{name} closed")
            if action == "open":
                action = "increase"
            elif action == "close":
                action = "decrease"

        if action in ("on", "off"):
            if not device.POWERED:
                return f"The {name} can't be switched {action}"
            return Plan(device, {"on": action == "on"}, f"{name} turned {action}")

        if action not in ("set", "increase", "decrease") or device.ADJUSTABLE is None:
            return f"I'm not sure how to {action} the {name}"
        return self._plan_level(cmd, device, action)

    def _plan_level(self, cmd: ParsedCommand, device: DeviceBase, action: str) -> Plan | str:
        attr = device.ADJUSTABLE
        assert attr is not None
        lo, hi = device.RANGE
        current = device.level() or 0.0
        is_on = getattr(device, "on", True)
        explanation: InferenceResult | None = None
        why = ""

        if cmd.value is not None:
            target = cmd.value
        elif cmd.delta is not None:
            target = current - cmd.delta if action == "decrease" else current + cmd.delta
        elif cmd.term == "comfortable":
            system = COMFORT_SYSTEMS.get(device.type)
            if system is None:
                return f"I don't have a comfort model for the {device.name} yet"
            explanation = system.infer(**self._comfort_inputs(device, system.inputs))
            target = explanation.value
            why = f" ({_describe_inputs(explanation)})"
            if action == "decrease" and is_on and target >= current:
                return (
                    f"The {device.name} is already at or below a comfortable level "
                    f"({device.format_level(current)}; comfortable is about {device.format_level(device.snap(target))})"
                )
            if action == "increase" and is_on and target <= current:
                return (
                    f"The {device.name} is already at or above a comfortable level "
                    f"({device.format_level(current)}; comfortable is about {device.format_level(device.snap(target))})"
                )
        elif cmd.term in ("max", "min"):
            target = hi if cmd.term == "max" else device.MIN_ON
        elif cmd.term is not None:
            variable = LEVEL_VARIABLES[device.type]
            term = TERM_ALIASES.get(device.type, {}).get(cmd.term, cmd.term)
            if term not in variable.terms:
                return f"I don't know what \"{cmd.term}\" means for the {device.name}"
            target = variable.term_value(term)
        else:
            if action == "set":
                return f"What level should I set the {device.name} to?"
            if not is_on and action == "increase":
                return Plan(device, {"on": True}, f"{device.name} turned on at {device.format_level()}")
            if not is_on and action == "decrease":
                return f"The {device.name} is already off"
            span = device.step_span()
            room_left = (hi - current) if action == "increase" else (current - lo)
            explanation = STEP_SIZE.infer(
                intensity=HEDGE_INTENSITY[cmd.hedge],
                headroom=min(100.0, room_left / span * 100),
            )
            step = max(device.STEP, explanation.value / 100 * span)
            target = current + step if action == "increase" else current - step

        target = device.snap(target)
        updates: dict[str, Any] = {attr: target}
        powered = device.POWERED
        if powered:
            # Brightness/speed of 0 means off; anything else implies on.
            turn_off = attr != "setpoint" and target <= 0
            updates["on"] = not turn_off
            if turn_off:
                updates.pop(attr)
        verb = {"increase": "raised", "decrease": "lowered"}.get(action, "set")
        if isinstance(device, Blinds):
            verb = "opened" if target > current else "closed"
        if powered and not updates["on"]:
            reply = f"{device.name} turned off"
        else:
            reply = f"{device.name} {verb} to {device.format_level(target)}{why}"
        payload = None
        if explanation is not None:
            payload = {"device_id": device.id, "device_name": device.name, **explanation.to_dict()}
        return Plan(device, updates, reply, payload)

    def _comfort_inputs(self, device: DeviceBase, needed: dict[str, Any]) -> dict[str, float]:
        env = self.home.rooms[device.room_id].environment
        available = {
            "temperature": env.temperature,
            "humidity": env.humidity,
            "ambient_light": env.ambient_light,
            "time_of_day": self.home.clock.hour(),
        }
        return {name: available[name] for name in needed}


class NeedsConfirmation(Exception):
    pass


def _describe_inputs(result: InferenceResult) -> str:
    parts = []
    for name, value in result.inputs.items():
        if name == "temperature":
            parts.append(f"{value:.1f}°C")
        elif name == "humidity":
            parts.append(f"{value:.0f}% humidity")
        elif name == "time_of_day":
            parts.append(f"{int(value):02d}:{int(value % 1 * 60):02d}")
        elif name == "ambient_light":
            parts.append(f"daylight {value:.0f}/100")
    return "comfortable for " + ", ".join(parts)


def _join(items: list[str]) -> str:
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " and " + items[-1]


def _sentence(text: str) -> str:
    text = text.strip()
    return text if text.endswith((".", "?", "!")) else text + "."


def _duration(minutes: float) -> str:
    total = round(minutes)
    hours, mins = divmod(total, 60)
    parts = []
    if hours:
        parts.append(f"{hours} hour{'s' if hours != 1 else ''}")
    if mins or not hours:
        parts.append(f"{mins} minute{'s' if mins != 1 else ''}")
    return " ".join(parts)


def timer_due(now: datetime, *, minutes: float | None = None, at: str | None = None) -> tuple[str, str]:
    """When a timer fires, as (ISO time, words like "23:30 (in 2 hours)").

    `minutes` counts from now; `at` is a clock time "HH:MM" (tomorrow if already past).
    """
    now = now.replace(microsecond=0)
    if minutes is not None:
        due = now + timedelta(minutes=minutes)
        return due.isoformat(), f"{due:%H:%M} (in {_duration(minutes)})"
    hour, minute = (int(x) for x in (at or "00:00").split(":"))
    due = now.replace(hour=hour, minute=minute, second=0)
    if due <= now:
        due += timedelta(days=1)
    return due.isoformat(), f"{due:%H:%M}" + (" tomorrow" if due.date() != now.date() else "")
