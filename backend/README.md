# Nestra backend

Python backend for the Nestra smart home dashboard: an appliance simulator,
a natural-language command parser, and a fuzzy-logic engine that turns vague
words ("comfortable", "a bit lower") into concrete device settings.

```
"lower the fan to a comfortable speed"
  → NLU (nestra/nlu)        {action: decrease, device: fan, term: comfortable}
  → Fuzzy (nestra/fuzzy)    temperature 27.5°C, humidity 65% → fan_speed 55%  (+ which rules fired)
  → Simulator (simulator/)  Air Circulator.speed 85 → 55, event pushed to the dashboard
```

## Setup

```bash
cd backend
python3 -m venv .venv
.venv/bin/pip install -e '.[dev]'
```

## Run

```bash
.venv/bin/python -m nestra.cli            # interactive console, no server needed
.venv/bin/uvicorn nestra.main:app --reload # API on http://127.0.0.1:8000 (docs at /docs)
.venv/bin/python -m pytest                 # tests
```

To use Firebase accounts and Firestore: save the service-account key as `var/firebase-admin.json`,
then `cp .env.example .env` and start with:

```bash
.venv/bin/uvicorn nestra.main:app --env-file .env
```

Environment variables:

| Variable | Default | Meaning |
|---|---|---|
| `NESTRA_AUTH` | `none` | `none` = no login, one shared home. `firebase` = Firebase ID token required, one home per user |
| `NESTRA_STORAGE` | `file` | `file` = JSON under `var/` (`var/homes/<uid>.json` per user). `firestore` = Firestore `homes/{uid}` |
| `NESTRA_FIREBASE_CREDENTIALS` | `var/firebase-admin.json` | Service-account key, needed for Firestore storage only. Git-ignored; never commit it |
| `NESTRA_NEW_HOME` | `starter` | New users start with empty rooms (`starter`) or the sample devices (`demo`) |
| `FIREBASE_AUTH_EMULATOR_HOST` | unset | e.g. `localhost:9099` to accept tokens from the local Auth emulator |
| `NESTRA_TIME_SCALE` | `10` | Simulated seconds per real second (0 freezes time) |
| `NESTRA_START_HOUR` | now | Start the simulated clock at this hour, e.g. `20.5` |
| `NESTRA_DEFAULT_ROOM` | `living_room` | Room the wall tablet is in, used when a command names no room |
| `NESTRA_HOME_CONFIG` | `nestra/data/home.json` | Rooms and devices to simulate |
| `NESTRA_STATE_FILE` | `var/home.json` | Where your rooms and devices are saved (delete it to reset to the demo home) |
| `NESTRA_WEB_DIR` | `../app/build/web` | Built Flutter dashboard served at `/` (skipped if missing) |

## Layout

```
nestra/
  data/home.json        rooms, devices, weather (edit to change the demo home)
  simulator/            device models, room physics (AC cools, daylight, humidity), activity log
  fuzzy/engine.py       Mamdani engine: membership functions, hedges, rules, explainable results
  fuzzy/rules.py        variables and rule bases: fan / AC / light comfort, relative step size
  nlu/parser.py         rule-based text → ParsedCommand (device, room, action, term, hedge)
  commands.py           pipeline: resolve devices, ask to clarify, run fuzzy, apply changes
  activity.py           readable before/after activity entries ("Fan speed High (85%) → Low (25%)")
  store.py              saving homes and history: JSON files or Firestore, written in the background
  auth.py               Firebase ID token verification (or no-login mode)
  sessions.py           one live home per signed-in user
  main.py               FastAPI REST + WebSocket
  cli.py                console for trying commands
```

## API for the Flutter app

REST:

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/home` | Full snapshot: time, outside weather, rooms with environment and devices, recent activity |
| GET | `/api/rooms/{id}` | One room |
| PATCH | `/api/devices/{id}` | Control, e.g. `{"on": true, "brightness": 60}`, or rename/move: `{"name": "...", "room_id": "..."}` |
| POST | `/api/devices` | Add a device: `{"type": "appliance", "name": "Kettle", "room_id": "kitchen", "kind": "kettle"}` |
| DELETE | `/api/devices/{id}` | Remove a device |
| POST | `/api/rooms` | Add a room: `{"name": "Garage"}` |
| PATCH / DELETE | `/api/rooms/{id}` | Rename (`{"name": ...}`) or remove a room and its devices |
| GET | `/api/catalog` | Device types and appliance kinds for the "Add device" form |
| POST | `/api/command` | `{"text": "...", "room_context"?: "bedroom", "confirm"?: false}` |
| GET | `/api/activity?limit=20` | Recent Activity: each entry has `changes` like `{"label": "Fan speed", "old_text": "High (85%)", "new_text": "Low (25%)"}` |
| GET | `/api/fuzzy` | All fuzzy systems with their variables and rules |
| POST | `/api/fuzzy/{system}` | Try a system: `{"inputs": {"temperature": 29, "humidity": 70}}` |

The `/api/command` response contains `reply` (text to show or speak), `changes`,
`explanations` (the fuzzy trace for the "why" panel), and either
`needs_clarification` with `options` (e.g. which room's AC) or
`needs_confirmation` (resend with `"confirm": true`, used for unlocking doors).

With `NESTRA_AUTH=firebase`, REST calls need `Authorization: Bearer <Firebase ID token>`
(401 otherwise) and the WebSocket's first message must be `{"type": "auth", "token": "..."}`.
`GET /api/me` returns the signed-in user.

WebSocket `/ws`:

- Server → client: `snapshot` on connect, then `device`, `environment`, `activity`, `command_result`, `error`, `pong`.
- Client → server: `{"type": "command", "text": "..."}`, `{"type": "snapshot"}`, `{"type": "ping"}`.

## Tuning the fuzzy rules

Edit `nestra/fuzzy/rules.py`. Rules are readable text:

```python
rule("temperature is warm and humidity is humid", "high")
rule("time_of_day is night", "high", weight=0.8)
```

Supported: `and` / `or` (not mixed in one rule), `not`, and hedges `very`, `extremely`, `somewhat`.
`test_rule_bases_cover_the_whole_input_space` fails if a change leaves inputs where no rule fires.
Use `POST /api/fuzzy/{system}` or the CLI to see which rules fire for given inputs.

## Next steps

- Voice: `POST /api/voice` that accepts audio and transcribes it with `faster-whisper`, then runs the same pipeline.
- Feelings: "I'm hot" → treat as comfort with a bias toward cooler.
- Optional LLM fallback in `nlu/` that returns the same `ParsedCommand` when the rule parser finds nothing.
