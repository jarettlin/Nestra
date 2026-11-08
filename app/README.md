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
