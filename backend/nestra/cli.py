"""Interactive console for trying commands without the UI.

    python -m nestra.cli --hour 14 --room living_room
    > lower the fan to a comfortable speed

Special inputs: ":state" prints the current room, ":rooms" lists rooms,
":room <id>" switches the tablet room, ":quit" exits. Prefix a command with
"!" to confirm a sensitive action (e.g. "!unlock the front door").
"""

from __future__ import annotations

import argparse

from .commands import CommandProcessor
from .simulator import Home, SimClock


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--hour", type=float, default=14.0, help="simulated time of day (default 14:00)")
    ap.add_argument("--room", default="living_room", help="room the tablet is in")
    ap.add_argument("command", nargs="*", help="run one command and exit")
    args = ap.parse_args()

    home = Home.from_file(clock=SimClock.at_hour(args.hour))
    processor = CommandProcessor(home)
    room = args.room

    def run(text: str) -> None:
        confirm = text.startswith("!")
        result = processor.execute(text.lstrip("!"), room_context=room, confirm=confirm, source="cli")
        print(f"  {result.reply}")
        for c in result.changes:
            print(f"    · {c.device_name}.{c.attribute}: {c.old} → {c.new}")
        for e in result.explanations:
            print(f"    why ({e['device_name']}, {e['system']}): {e['output']} = {e['value']} [{e['term']}]")
            for r in e["rules"][:3]:
                print(f"      {r['strength']:.2f}  {r['rule']}")

    if args.command:
        run(" ".join(args.command))
        return

    print(f"Nestra console · {home.clock.now():%H:%M} · tablet in {home.rooms[room].name}. :quit to exit.")
    while True:
        try:
            text = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not text:
            continue
        if text == ":quit":
            break
        if text == ":rooms":
            print("  " + ", ".join(home.rooms))
        elif text.startswith(":room "):
            new_room = text.split(maxsplit=1)[1]
            if new_room in home.rooms:
                room = new_room
            else:
                print(f"  unknown room {new_room!r}")
        elif text == ":state":
            snap = home.room_snapshot(room)
            print(f"  {snap['name']}: {snap['environment']}")
            for d in snap["devices"]:
                print(f"    {d}")
        else:
            run(text)


if __name__ == "__main__":
    main()
