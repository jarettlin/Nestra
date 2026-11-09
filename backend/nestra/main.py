"""FastAPI app: REST for the dashboard, WebSocket for live updates.

Run:  uvicorn nestra.main:app --reload
Docs: http://127.0.0.1:8000/docs

Every request works on the caller's own home. With NESTRA_AUTH=firebase the
caller is identified by a Firebase ID token; with NESTRA_AUTH=none (default)
everyone shares one local home.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import os
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, ValidationError

from . import activity
from .auth import (
    Authenticator,
    AuthError,
    FirebaseAuth,
    NoAuth,
    UserInfo,
    find_project_id,
    firebase_app,
    require_credentials,
)
from .commands import timer_due
from .fuzzy.engine import NoRuleFired
from .fuzzy.rules import SYSTEMS
from .sessions import HomeSession, SessionManager
from .simulator import Home, SimClock
from .simulator.devices import APPLIANCE_KINDS, DEVICE_CLASSES, DEVICE_TYPE_LABELS
from .simulator.home import DEFAULT_CONFIG, Environment, HomeConfig, Room
from .store import FirestoreStore, HomeStore, JsonFileStore
from .voice import SpeechToText, vocabulary_hint
from . import replies
from .wake import split_wake

# A child of uvicorn's logger, so these lines show in the server output.
log = logging.getLogger("uvicorn.error.nestra")

MAX_AUDIO_BYTES = 10 * 1024 * 1024  # ~10 minutes of compressed speech; commands are a few seconds

BACKEND_DIR = Path(__file__).resolve().parents[1]
DEFAULT_WEB_DIR = BACKEND_DIR.parent / "app" / "build" / "web"
DEFAULT_STATE_FILE = BACKEND_DIR / "var" / "home.json"
DEFAULT_CREDENTIALS = BACKEND_DIR / "var" / "firebase-admin.json"
# What a new user's home starts with: room -> [(type, name, extra attributes)].
STARTER_HOME: dict[str, list[tuple[str, str, dict[str, Any]]]] = {
    "Living Room": [
        ("light", "Main Light", {"brightness": 80}),
        ("fan", "Ceiling Fan", {"speed": 40}),
        ("ac", "Aircond", {"setpoint": 25}),
    ],
    "Bedroom": [
        ("light", "Main Light", {"brightness": 60}),
        ("fan", "Ceiling Fan", {"speed": 30}),
        ("ac", "Aircond", {"setpoint": 26}),
    ],
    "Kitchen": [
        ("light", "Main Light", {"brightness": 90}),
        ("fan", "Ceiling Fan", {"speed": 40}),
    ],
}


def _env_float(name: str, default: float | None) -> float | None:
    raw = os.getenv(name)
    return float(raw) if raw else default


def _env_path(name: str, default: Path) -> Path:
    """Path setting; relative paths are taken from the backend folder, wherever uvicorn runs."""
    path = Path(os.getenv(name, default))
    return path if path.is_absolute() else BACKEND_DIR / path


@dataclass
class Settings:
    """Read from environment variables when created."""

    # none = no login, one shared local home. firebase = Firebase ID tokens required.
    auth: str = field(default_factory=lambda: os.getenv("NESTRA_AUTH", "none"))
    # file = JSON files under var/. firestore = Firestore (needs Firebase credentials).
    storage: str = field(default_factory=lambda: os.getenv("NESTRA_STORAGE", "file"))
    # Service-account key for the Firebase Admin SDK. Never commit it.
    firebase_credentials: Path = field(default_factory=lambda: _env_path("NESTRA_FIREBASE_CREDENTIALS", DEFAULT_CREDENTIALS))
    firebase_project: str | None = field(default_factory=lambda: os.getenv("NESTRA_FIREBASE_PROJECT"))
    # What a brand-new user's home starts as: "starter" (empty rooms) or "demo" (sample devices).
    new_home: str = field(default_factory=lambda: os.getenv("NESTRA_NEW_HOME", "starter"))

    home_config: Path = field(default_factory=lambda: _env_path("NESTRA_HOME_CONFIG", DEFAULT_CONFIG))
    # Simulated seconds per real second. 10 makes room temperature visibly react to the AC.
    time_scale: float = field(default_factory=lambda: _env_float("NESTRA_TIME_SCALE", 10.0))
    # Pin the simulated start time (e.g. 20.5 = 20:30) to demo evening behaviour.
    start_hour: float | None = field(default_factory=lambda: _env_float("NESTRA_START_HOUR", None))
    tick_seconds: float = field(default_factory=lambda: _env_float("NESTRA_TICK_SECONDS", 1.0))
    # Room the wall tablet is mounted in; used when a command doesn't name a room.
    default_room: str | None = field(default_factory=lambda: os.getenv("NESTRA_DEFAULT_ROOM", "living_room"))
    # Built Flutter web app to serve at "/". Run `flutter build web` in app/ first.
    web_dir: Path = field(default_factory=lambda: _env_path("NESTRA_WEB_DIR", DEFAULT_WEB_DIR))
    # File storage: the shared local home, and one file per signed-in user.
    state_file: Path = field(default_factory=lambda: _env_path("NESTRA_STATE_FILE", DEFAULT_STATE_FILE))
    homes_dir: Path = field(default_factory=lambda: _env_path("NESTRA_HOMES_DIR", BACKEND_DIR / "var" / "homes"))


class CommandRequest(BaseModel):
    text: str = Field(min_length=1, examples=["lower the fan to a comfortable speed"])
    room_context: str | None = Field(None, description="Room the request came from; defaults to the tablet's room")
    confirm: bool = Field(False, description="Set true to confirm a sensitive action such as unlocking")


class RoomRequest(BaseModel):
    name: str = Field(min_length=1, max_length=40, examples=["Kitchen"])


class NewDeviceRequest(BaseModel):
    type: str = Field(examples=["appliance"])
    name: str = Field("", max_length=40, examples=["Kettle"], description="Blank = a default like \"Aircond\" or \"TV\"")
    room_id: str = Field(examples=["kitchen"])
    kind: str | None = Field(None, description="Appliance kind, e.g. tv, kettle (appliances only)")


class FuzzyRequest(BaseModel):
    inputs: dict[str, float] = Field(examples=[{"temperature": 29, "humidity": 70}])


# --------------------------------------------------------------------------- wiring
def _demo_config(settings: Settings) -> HomeConfig:
    return HomeConfig.model_validate_json(Path(settings.home_config).read_text())


def _starter_config(settings: Settings) -> HomeConfig:
    """Common rooms with the usual devices, all switched off, ready to use or rename."""
    weather = _demo_config(settings).weather
    rooms, devices = [], []
    for room_name, room_devices in STARTER_HOME.items():
        room_id = room_name.lower().replace(" ", "_")
        rooms.append(
            Room(
                id=room_id,
                name=room_name,
                environment=Environment(temperature=weather.mean_temperature - 1, humidity=weather.humidity - 5),
            )
        )
        for device_type, name, extra in room_devices:
            slug = name.lower().replace(" ", "_")
            devices.append(
                {"id": f"{room_id}_{slug}", "type": device_type, "name": name, "room_id": room_id, **extra}
            )
    return HomeConfig.model_validate(
        {"name": "My Home", "weather": weather.model_dump(), "rooms": [r.model_dump() for r in rooms], "devices": devices}
    )


def _build_auth(settings: Settings) -> Authenticator:
    if settings.auth == "none":
        return NoAuth()
    if settings.auth == "firebase":
        project = find_project_id(settings.firebase_credentials, settings.firebase_project)
        return FirebaseAuth(firebase_app(settings.firebase_credentials, project))
    raise ValueError(f"NESTRA_AUTH must be 'none' or 'firebase', not {settings.auth!r}")


def _build_store_factory(settings: Settings):
    if settings.storage == "firestore":
        from firebase_admin import firestore

        require_credentials(settings.firebase_credentials)
        project = find_project_id(settings.firebase_credentials, settings.firebase_project)
        client = firestore.client(firebase_app(settings.firebase_credentials, project))
        return lambda uid: FirestoreStore(client, uid)
    if settings.storage == "file":
        def file_store(uid: str) -> HomeStore:
            if uid == "local":
                return JsonFileStore(settings.state_file)
            safe = "".join(c for c in uid if c.isalnum() or c in "-_")
            return JsonFileStore(settings.homes_dir / f"{safe}.json")
        return file_store
    raise ValueError(f"NESTRA_STORAGE must be 'file' or 'firestore', not {settings.storage!r}")


def _bearer(request: Request) -> str | None:
    header = request.headers.get("authorization", "")
    return header[7:].strip() if header.lower().startswith("bearer ") else None


def create_app(
    home: Home | None = None,
    settings: Settings | None = None,
    *,
    simulate: bool = True,
    store: HomeStore | None = None,
    authenticator: Authenticator | None = None,
    speech: SpeechToText | None = None,
) -> FastAPI:
    """Build the app.

    Passing `home` (as tests do) uses that one home for the local user, saved
    only if a `store` is given.
    """
    settings = settings or Settings()
    clock = (
        SimClock.at_hour(settings.start_hour, scale=settings.time_scale)
        if settings.start_hour is not None
        else SimClock(scale=settings.time_scale)
    )
    authenticator = authenticator or _build_auth(settings)
    speech = speech or SpeechToText()

    def new_home(uid: str) -> HomeConfig:
        # The shared local home starts as the demo so there's something to play with.
        if uid == "local" or settings.new_home == "demo":
            return _demo_config(settings)
        return _starter_config(settings)

    manager = SessionManager(
        clock=home.clock if home else clock,
        store_for=(lambda uid: store) if home else _build_store_factory(settings),
        new_home=new_home,
    )
    if home is not None:
        manager.add("local", home, store)

    async def simulation_loop() -> None:
        while True:
            await asyncio.sleep(settings.tick_seconds)
            manager.tick(settings.tick_seconds * manager.clock.scale / 60)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        task = asyncio.create_task(simulation_loop()) if simulate else None
        if simulate and not speech.loaded:
            speech.preload_in_background()  # so the first voice command isn't slow
        yield
        if task:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task
        manager.flush()

    app = FastAPI(title="Nestra", version="0.2.0", lifespan=lifespan)
    app.state.manager = manager
    app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

    def current_user(request: Request) -> UserInfo:
        try:
            return authenticator.verify(_bearer(request))
        except AuthError as e:
            raise HTTPException(401, str(e)) from e

    def current_session(user: UserInfo = Depends(current_user)) -> HomeSession:
        return manager.get(user.uid)

    def run_command(session: HomeSession, req: CommandRequest, source: str) -> dict[str, Any]:
        home = session.home
        if req.room_context is not None and req.room_context not in home.rooms:
            raise HTTPException(404, f"Unknown room {req.room_context!r}")
        room = req.room_context or (settings.default_room if settings.default_room in home.rooms else None)
        return session.processor.execute(req.text, room_context=room, confirm=req.confirm, source=source).to_dict()

    def _answered_room(session: HomeSession, text: str) -> str | None:
        """'The bedroom one' / 'kitchen' -> that room's id, if the answer is only a room."""
        parser = session.processor.parser
        rooms = parser._match_rooms(text.lower())
        parsed = parser.parse(text)
        names_device = any(p.device_ids or (p.device_types and p.action) for p in parsed)
        return rooms[0] if len(rooms) == 1 and not names_device else None

    def guard(fn):
        """Map model errors to HTTP errors."""
        try:
            return fn()
        except KeyError as e:
            raise HTTPException(404, f"Unknown id {e.args[0]!r}") from e
        except ValidationError as e:
            raise HTTPException(422, e.errors(include_url=False, include_context=False)) from e
        except ValueError as e:
            raise HTTPException(422, str(e)) from e

    # ------------------------------------------------------------------ REST
    @app.get("/api/health")
    def health() -> dict[str, Any]:
        return {"ok": True, "time": manager.clock.now().isoformat(timespec="seconds"), "auth": authenticator.mode}

    @app.get("/api/me")
    def me(user: UserInfo = Depends(current_user)) -> dict[str, Any]:
        return {"uid": user.uid, "email": user.email, "name": user.name, "auth": authenticator.mode}

    @app.get("/api/home")
    def get_home(s: HomeSession = Depends(current_session)) -> dict[str, Any]:
        return s.home.snapshot()

    @app.get("/api/catalog")
    def get_catalog() -> dict[str, Any]:
        """Device types and appliance kinds the "Add device" form can offer."""
        return {
            "device_types": [{"type": t, "label": DEVICE_TYPE_LABELS[t]} for t in DEVICE_CLASSES],
            "appliance_kinds": [{"kind": k, "label": label} for k, (label, _) in APPLIANCE_KINDS.items()],
        }

    @app.get("/api/rooms/{room_id}")
    def get_room(room_id: str, s: HomeSession = Depends(current_session)) -> dict[str, Any]:
        if room_id not in s.home.rooms:
            raise HTTPException(404, f"Unknown room {room_id!r}")
        return s.home.room_snapshot(room_id)

    @app.post("/api/rooms", status_code=201)
    def create_room(req: RoomRequest, s: HomeSession = Depends(current_session)) -> dict[str, Any]:
        room = guard(lambda: s.home.add_room(req.name))
        return s.home.room_snapshot(room.id)

    @app.patch("/api/rooms/{room_id}")
    def update_room(room_id: str, req: RoomRequest, s: HomeSession = Depends(current_session)) -> dict[str, Any]:
        guard(lambda: s.home.rename_room(room_id, req.name))
        return s.home.room_snapshot(room_id)

    @app.delete("/api/rooms/{room_id}")
    def delete_room(room_id: str, s: HomeSession = Depends(current_session)) -> dict[str, Any]:
        return {"removed_devices": guard(lambda: s.home.remove_room(room_id))}

    @app.get("/api/devices/{device_id}")
    def get_device(device_id: str, s: HomeSession = Depends(current_session)) -> dict[str, Any]:
        if device_id not in s.home.devices:
            raise HTTPException(404, f"Unknown device {device_id!r}")
        return s.home.devices[device_id].model_dump()

    @app.post("/api/devices", status_code=201)
    def create_device(req: NewDeviceRequest, s: HomeSession = Depends(current_session)) -> dict[str, Any]:
        if req.type not in DEVICE_CLASSES:
            raise HTTPException(422, f"Unknown device type {req.type!r}")
        extra = {"kind": req.kind} if req.type == "appliance" and req.kind else {}
        return guard(lambda: s.home.add_device(req.type, req.name, req.room_id, **extra)).model_dump()

    @app.delete("/api/devices/{device_id}")
    def delete_device(device_id: str, s: HomeSession = Depends(current_session)) -> dict[str, Any]:
        guard(lambda: s.home.remove_device(device_id))
        return {"ok": True}

    @app.patch("/api/devices/{device_id}")
    def patch_device(
        device_id: str, updates: dict[str, Any], s: HomeSession = Depends(current_session)
    ) -> dict[str, Any]:
        """Control a device (on, brightness, speed...) or rename/move it (name, room_id)."""
        home = s.home
        if device_id not in home.devices:
            raise HTTPException(404, f"Unknown device {device_id!r}")
        structural = {k: updates.pop(k) for k in ("name", "room_id") if k in updates}
        # Timers by the simulated clock: {"timer_off_in": 30} (minutes) or {"timer_on_at_time": "07:00"}.
        for which in ("on", "off"):
            minutes = updates.pop(f"timer_{which}_in", None)
            at = updates.pop(f"timer_{which}_at_time", None)
            if minutes is not None or at is not None:
                try:
                    updates[f"timer_{which}_at"], _ = timer_due(
                        home.clock.now(), minutes=float(minutes) if minutes is not None else None, at=at
                    )
                except (TypeError, ValueError) as e:
                    raise HTTPException(422, f"Invalid timer: {e}") from e
        kind_changed = "kind" in updates and updates["kind"] != getattr(home.devices[device_id], "kind", None)

        def apply() -> list:
            changes = home.edit_device(device_id, **structural, source="manual") if structural else []
            changes += home.update_device(device_id, updates, source="manual") if updates else []
            return changes

        changes = guard(apply)
        if kind_changed:
            home.structure_version += 1  # appliance kind changes the words that match it
        activity.record(home, device_id, changes, source="manual")
        return {"device": home.devices[device_id].model_dump(), "changes": [c.to_dict() for c in changes]}

    @app.post("/api/command")
    def post_command(req: CommandRequest, s: HomeSession = Depends(current_session)) -> dict[str, Any]:
        """Natural-language command (typed, or the transcript from speech-to-text)."""
        return run_command(s, req, source="voice")

    @app.post("/api/voice")
    def post_voice(
        audio: UploadFile = File(..., description="Recorded speech (webm, ogg, mp4/m4a, wav...)"),
        room_context: str | None = Form(None),
        confirm: bool = Form(False),
        wake: bool = Form(False, description="Hands-free: act only if it starts with \"Hi Nestra\""),
        conversation: bool = Form(False, description="Follow-up in a hands-free conversation: no wake phrase needed"),
        previous: str | None = Form(None, description="Command Nestra just asked about (which room? / go ahead?)"),
        s: HomeSession = Depends(current_session),
    ) -> dict[str, Any]:
        """Spoken command: transcribe with Whisper, then run it like /api/command.

        With wake=true (hands-free listening) speech without the wake phrase is
        ignored; "Hi Nestra" alone asks the app to listen for the command.
        With conversation=true (just after a reply) no wake phrase is needed,
        and "thank you" / "that's all" ends the conversation (end=true).
        """
        data = audio.file.read(MAX_AUDIO_BYTES + 1)
        if not data:
            raise HTTPException(422, "No audio received")
        if len(data) > MAX_AUDIO_BYTES:
            raise HTTPException(413, "Recording is too long")
        try:
            heard = speech.transcribe(data, hint=vocabulary_hint(s.home))
        except Exception as e:
            raise HTTPException(422, "Couldn't read that recording. Please try again.") from e
        woke = split_wake(heard.text)
        if wake and not conversation and not woke.heard:
            # Ordinary conversation near the mic: drop it, and keep it out of the logs.
            log.info("Wake: %d bytes, no wake phrase (%.2fs)", len(data), heard.seconds)
            return {"ok": False, "woke": False, "reply": "", "transcript_seconds": round(heard.seconds, 2)}
        mode = "conversation" if conversation else "wake" if wake else "push-to-talk"
        log.info("Voice (%s): %d bytes -> %r in %.2fs", mode, len(data), heard.text, heard.seconds)
        extra = {"transcript": heard.text, "transcribe_seconds": round(heard.seconds, 2), "woke": woke.heard}
        # "Hi Nestra, turn on the fan" works in push-to-talk too.
        command = woke.command if woke.heard else heard.text
        hands_free = wake or conversation
        if not command.strip(" .,!?"):
            if woke.heard:
                return {"ok": True, "listen": True, "reply": replies.wake_reply(), **extra}
            return {"ok": False, "reply": "I didn't catch that. Please try again.", **extra}
        if previous:
            # Answering Nestra's question: "yes" / "no", or a room for "which fan?".
            if replies.is_yes(command):
                command, confirm = previous, True
            elif replies.is_no(command):
                return {"ok": True, "reply": replies.declined(), **extra, "command": command}
            elif room := _answered_room(s, command):
                command, room_context = previous, room
        if hands_free and replies.is_goodbye(command):
            return {"ok": True, "end": True, "reply": replies.goodbye(), **extra, "command": command}
        req = CommandRequest(text=command, room_context=room_context, confirm=confirm)
        result = replies.friendly(run_command(s, req, source="voice"), follow_up=hands_free)
        return {**result, **extra, "command": command}

    @app.get("/api/activity")
    def get_activity(limit: int = 20, s: HomeSession = Depends(current_session)) -> list[dict[str, Any]]:
        return [a.model_dump() for a in list(s.home.activity)[: max(1, min(limit, 200))]]

    @app.get("/api/fuzzy")
    def list_fuzzy_systems() -> dict[str, Any]:
        return {
            name: {
                "inputs": {v.name: {"range": [v.lo, v.hi], "terms": list(v.terms)} for v in sys.inputs.values()},
                "output": {"name": sys.output.name, "range": [sys.output.lo, sys.output.hi], "terms": list(sys.output.terms)},
                "rules": [r.describe(sys.output.name) for r in sys.rules],
            }
            for name, sys in SYSTEMS.items()
        }

    @app.post("/api/fuzzy/{system}")
    def run_fuzzy(system: str, req: FuzzyRequest) -> dict[str, Any]:
        """Playground for tuning rules: run one fuzzy system on any inputs."""
        if system not in SYSTEMS:
            raise HTTPException(404, f"Unknown fuzzy system {system!r}")
        try:
            return SYSTEMS[system].infer(**req.inputs).to_dict()
        except (ValueError, NoRuleFired) as e:
            raise HTTPException(422, str(e)) from e

    # ------------------------------------------------------------- WebSocket
    @app.websocket("/ws")
    async def websocket(ws: WebSocket) -> None:
        """First client message must be {"type": "auth", "token": "<Firebase ID token>"}
        (ignored when auth is off). Then:
        Server -> client: snapshot, device, environment, activity, command_result, error.
        Client -> server: {"type": "command", "text": ..., "room_context"?, "confirm"?},
        {"type": "snapshot"} or {"type": "ping"}.
        """
        await ws.accept()
        try:
            user = await _authenticate_ws(ws, authenticator)
        except (AuthError, asyncio.TimeoutError, WebSocketDisconnect, ValueError) as e:
            with contextlib.suppress(Exception):
                await ws.send_json({"type": "error", "data": {"message": str(e) or "Sign in required", "code": 401}})
                await ws.close(code=4401)
            return

        session = manager.get(user.uid)
        queue = session.hub.register()
        queue.put_nowait({"type": "snapshot", "data": session.home.snapshot()})

        async def pump() -> None:
            while True:
                await ws.send_json(await queue.get())

        sender = asyncio.create_task(pump())
        try:
            while True:
                msg = await ws.receive_json()
                kind = msg.get("type") if isinstance(msg, dict) else None
                if kind == "command":
                    try:
                        req = CommandRequest.model_validate({k: v for k, v in msg.items() if k != "type"})
                        queue.put_nowait({"type": "command_result", "data": run_command(session, req, "voice")})
                    except (ValidationError, HTTPException) as e:
                        queue.put_nowait({"type": "error", "data": {"message": str(e)}})
                elif kind == "ping":
                    queue.put_nowait({"type": "pong"})
                elif kind == "snapshot":
                    queue.put_nowait({"type": "snapshot", "data": session.home.snapshot()})
                elif kind == "auth":
                    pass  # token refresh; the connection is already authenticated
                else:
                    queue.put_nowait({"type": "error", "data": {"message": f"Unknown message type {kind!r}"}})
        except WebSocketDisconnect:
            pass
        finally:
            session.hub.unregister(queue)
            sender.cancel()

    # Serve the built Flutter dashboard (app/build/web) at "/" when it exists,
    # so one server hosts both the API and the UI.
    if settings.web_dir.is_dir():
        app.mount("/", StaticFiles(directory=settings.web_dir, html=True), name="web")

    return app


async def _authenticate_ws(ws: WebSocket, authenticator: Authenticator) -> UserInfo:
    if authenticator.mode == "none":
        return authenticator.verify(None)
    raw = await asyncio.wait_for(ws.receive_text(), timeout=10)
    msg = json.loads(raw)
    if not isinstance(msg, dict) or msg.get("type") != "auth":
        raise AuthError("Sign in required")
    return authenticator.verify(msg.get("token"))


app = create_app()
