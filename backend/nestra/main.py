"""FastAPI app: REST for the dashboard, WebSocket for live updates.

Run:  uvicorn nestra.main:app --reload
Docs: http://127.0.0.1:8000/docs
"""

from __future__ import annotations

import asyncio
import contextlib
import os
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, ValidationError

from .commands import CommandProcessor
from .fuzzy.engine import NoRuleFired
from .fuzzy.rules import SYSTEMS
from .simulator import Home, SimClock
from .simulator.home import DEFAULT_CONFIG


DEFAULT_WEB_DIR = Path(__file__).resolve().parents[2] / "app" / "build" / "web"


def _env_float(name: str, default: float | None) -> float | None:
    raw = os.getenv(name)
    return float(raw) if raw else default


@dataclass
class Settings:
    """Read from environment variables when created."""

    home_config: Path = field(default_factory=lambda: Path(os.getenv("NESTRA_HOME_CONFIG", DEFAULT_CONFIG)))
    # Simulated seconds per real second. 10 makes room temperature visibly react to the AC.
    time_scale: float = field(default_factory=lambda: _env_float("NESTRA_TIME_SCALE", 10.0))
    # Pin the simulated start time (e.g. 20.5 = 20:30) to demo evening behaviour.
    start_hour: float | None = field(default_factory=lambda: _env_float("NESTRA_START_HOUR", None))
    tick_seconds: float = field(default_factory=lambda: _env_float("NESTRA_TICK_SECONDS", 1.0))
    # Room the wall tablet is mounted in; used when a command doesn't name a room.
    default_room: str | None = field(default_factory=lambda: os.getenv("NESTRA_DEFAULT_ROOM", "living_room"))
    # Built Flutter web app to serve at "/". Run `flutter build web` in app/ first.
    web_dir: Path = field(default_factory=lambda: Path(os.getenv("NESTRA_WEB_DIR", DEFAULT_WEB_DIR)))


class Hub:
    """Fans Home events out to every connected WebSocket client."""

    def __init__(self, max_queue: int = 256) -> None:
        self._clients: set[asyncio.Queue[dict[str, Any]]] = set()
        self._max_queue = max_queue

    def register(self) -> asyncio.Queue[dict[str, Any]]:
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(self._max_queue)
        self._clients.add(queue)
        return queue

    def unregister(self, queue: asyncio.Queue[dict[str, Any]]) -> None:
        self._clients.discard(queue)

    def publish(self, message: dict[str, Any]) -> None:
        for queue in list(self._clients):
            with contextlib.suppress(asyncio.QueueFull):  # slow client: drop, it can resync
                queue.put_nowait(message)


class CommandRequest(BaseModel):
    text: str = Field(min_length=1, examples=["lower the fan to a comfortable speed"])
    room_context: str | None = Field(None, description="Room the request came from; defaults to the tablet's room")
    confirm: bool = Field(False, description="Set true to confirm a sensitive action such as unlocking")


class FuzzyRequest(BaseModel):
    inputs: dict[str, float] = Field(examples=[{"temperature": 29, "humidity": 70}])


def create_app(home: Home | None = None, settings: Settings | None = None, *, simulate: bool = True) -> FastAPI:
    settings = settings or Settings()
    if home is None:
        clock = (
            SimClock.at_hour(settings.start_hour, scale=settings.time_scale)
            if settings.start_hour is not None
            else SimClock(scale=settings.time_scale)
        )
        home = Home.from_file(settings.home_config, clock=clock)
    processor = CommandProcessor(home)
    hub = Hub()
    home.subscribe(hub.publish)

    async def simulation_loop() -> None:
        dt_minutes = settings.tick_seconds * home.clock.scale / 60
        while True:
            await asyncio.sleep(settings.tick_seconds)
            home.tick(dt_minutes)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        home.log("Simulator started", detail=f"time x{home.clock.scale:g}")
        task = asyncio.create_task(simulation_loop()) if simulate else None
        yield
        if task:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task

    app = FastAPI(title="Nestra", version="0.1.0", lifespan=lifespan)
    app.state.home = home
    app.state.processor = processor
    app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

    def run_command(req: CommandRequest, source: str) -> dict[str, Any]:
        room = req.room_context or settings.default_room
        if room is not None and room not in home.rooms:
            raise HTTPException(404, f"Unknown room {room!r}")
        return processor.execute(req.text, room_context=room, confirm=req.confirm, source=source).to_dict()

    # ------------------------------------------------------------------ REST
    @app.get("/api/health")
    def health() -> dict[str, Any]:
        return {"ok": True, "time": home.clock.now().isoformat(timespec="seconds")}

    @app.get("/api/home")
    def get_home() -> dict[str, Any]:
        return home.snapshot()

    @app.get("/api/rooms/{room_id}")
    def get_room(room_id: str) -> dict[str, Any]:
        if room_id not in home.rooms:
            raise HTTPException(404, f"Unknown room {room_id!r}")
        return home.room_snapshot(room_id)

    @app.get("/api/devices/{device_id}")
    def get_device(device_id: str) -> dict[str, Any]:
        if device_id not in home.devices:
            raise HTTPException(404, f"Unknown device {device_id!r}")
        return home.devices[device_id].model_dump()

    @app.patch("/api/devices/{device_id}")
    def patch_device(device_id: str, updates: dict[str, Any]) -> dict[str, Any]:
        """Manual control from the dashboard (toggles, sliders)."""
        if device_id not in home.devices:
            raise HTTPException(404, f"Unknown device {device_id!r}")
        try:
            changes = home.update_device(device_id, updates, source="manual")
        except ValidationError as e:
            raise HTTPException(422, e.errors(include_url=False, include_context=False)) from e
        except ValueError as e:
            raise HTTPException(422, str(e)) from e
        device = home.devices[device_id]
        if changes:
            summary = ", ".join(f"{c.attribute} → {c.new}" for c in changes)
            home.log(f"{home.rooms[device.room_id].name} · {device.name}", detail=summary, source="manual")
        return {"device": device.model_dump(), "changes": [c.to_dict() for c in changes]}

    @app.post("/api/command")
    def post_command(req: CommandRequest) -> dict[str, Any]:
        """Natural-language command (typed, or the transcript from speech-to-text)."""
        return run_command(req, source="voice")

    @app.get("/api/activity")
    def get_activity(limit: int = 20) -> list[dict[str, Any]]:
        return [a.model_dump() for a in list(home.activity)[: max(1, min(limit, 200))]]

    @app.get("/api/fuzzy")
    def list_fuzzy_systems() -> dict[str, Any]:
        return {
            name: {
                "inputs": {
                    v.name: {"range": [v.lo, v.hi], "terms": list(v.terms)} for v in s.inputs.values()
                },
                "output": {"name": s.output.name, "range": [s.output.lo, s.output.hi], "terms": list(s.output.terms)},
                "rules": [r.describe(s.output.name) for r in s.rules],
            }
            for name, s in SYSTEMS.items()
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
        """Server -> client: snapshot, device, environment, activity, command_result, error.
        Client -> server: {"type": "command", "text": ..., "room_context"?, "confirm"?} or {"type": "ping"}.
        """
        await ws.accept()
        queue = hub.register()
        queue.put_nowait({"type": "snapshot", "data": home.snapshot()})

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
                        result = run_command(req, source="voice")
                        queue.put_nowait({"type": "command_result", "data": result})
                    except (ValidationError, HTTPException) as e:
                        queue.put_nowait({"type": "error", "data": {"message": str(e)}})
                elif kind == "ping":
                    queue.put_nowait({"type": "pong"})
                elif kind == "snapshot":
                    queue.put_nowait({"type": "snapshot", "data": home.snapshot()})
                else:
                    queue.put_nowait({"type": "error", "data": {"message": f"Unknown message type {kind!r}"}})
        except WebSocketDisconnect:
            pass
        finally:
            hub.unregister(queue)
            sender.cancel()

    # Serve the built Flutter dashboard (app/build/web) at "/" when it exists,
    # so one server hosts both the API and the UI.
    if settings.web_dir.is_dir():
        app.mount("/", StaticFiles(directory=settings.web_dir, html=True), name="web")

    return app


app = create_app()
