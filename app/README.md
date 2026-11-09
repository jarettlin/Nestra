# Nestra dashboard (Flutter)

Dark in-wall tablet dashboard for Nestra, based on the "Luma" smart home design.
It shows the selected room's devices, a grid of rooms and a live Recent Activity
timeline, and takes natural-language commands through the mic button.

## Run

Start the backend first (see [../backend/README.md](../backend/README.md)), then either:

**Served by the backend (simplest, no Chrome needed):**

```bash
flutter build web
```

Then open http://localhost:8000. The backend serves `app/build/web` at `/`.

**Hot reload while developing** (open the printed URL in any browser):

```bash
flutter run -d web-server --web-port 8080
```

Point the app at another backend with `--dart-define=NESTRA_API=http://192.168.1.20:8000`,
and show a name in the greeting with `--dart-define=NESTRA_USER=Alex`.

## Voice

Tap the mic: Nestra records until you stop talking, the backend transcribes it
locally with Whisper, runs the command and the reply is spoken back (mute with
the speaker icon). Use a real browser such as Safari or Chrome and allow
microphone access; the Claude app's built-in browser pane blocks the microphone.

**Hands-free ("Hi Nestra"):** tap the ear button next to the mic. The mic stays
open and each burst of speech (never silence) is sent to the local backend,
which transcribes it and acts only if it starts with "Hi Nestra" / "Hey Nestra".
Say "Hi Nestra" and wait for "Yes?", or say it all at once: "Hi Nestra, turn on
the kitchen light". Everything else is discarded and not logged.
After answering, Nestra keeps listening for a follow-up without the wake phrase
("and dim the bedroom light", or "bedroom" / "yes" when it asked something);
"thank you", "that's all" or about 8 seconds of quiet ends the conversation. Keep the tab
open and in front: browsers pause the mic in background tabs.

## Sign-in (Firebase Auth)

The app opens on a login screen (email/password or Google) and sends the user's
Firebase ID token to the backend, which keeps a separate home for each account.

### Local testing with the Auth emulator

No real accounts needed: run the Firebase Auth emulator and point both sides at it.

```bash
firebase emulators:start --only auth
```

```bash
cd ../backend && NESTRA_AUTH=firebase FIREBASE_AUTH_EMULATOR_HOST=localhost:9099 .venv/bin/uvicorn nestra.main:app
```

```bash
flutter build web --dart-define=NESTRA_AUTH_EMULATOR=localhost:9099
```

Emulator test account (exists only in the emulator, which forgets it when stopped;
create it from the login screen): `tester@nestra.test` / `nestra-emulator-1`.

## Structure

```
lib/
  config.dart             backend URL and build-time settings
  models.dart             Device, Room, ActivityEntry, CommandResult, Explanation
  services/api.dart       REST: device updates and commands
  services/live.dart      WebSocket with automatic reconnect
  state/home_controller.dart  app state, applies live events, optimistic updates
  theme.dart              Luma colours, fonts, device icons
  ui/dashboard.dart       layout: header, room devices, rooms grid, activity panel
  ui/device_tile.dart     per-type controls: brightness bar, fan speeds, setpoint, blinds, lock
  ui/room_card.dart       room summary, room power switch, unlock button
  ui/activity_panel.dart  Recent Activity timeline and connection status
  ui/command_dialog.dart  command box, clarify/confirm follow-ups, fuzzy "why" view
```

Commands default to the room you have selected, so "turn on the fan" means the fan
in the room on screen.

## Tests

```bash
flutter analyze
```

```bash
flutter test
```
