"""One live home per signed-in user.

A user's home is loaded from the store the first time they connect, then kept
in memory: the simulator ticks it, commands change it, and every change is
saved back in the background.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import threading
from dataclasses import dataclass, field
from typing import Any, Callable

from .commands import CommandProcessor
from .simulator import Home, SimClock
from .simulator.home import HomeConfig
from .store import HomeStore, StoreWriter

ACTIVITY_TO_LOAD = 50
log = logging.getLogger("nestra.sessions")


class Hub:
    """Fans one home's events out to that user's connected WebSocket clients."""

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


@dataclass
class HomeSession:
    uid: str
    home: Home
    processor: CommandProcessor
    hub: Hub
    writer: StoreWriter | None = None


@dataclass
class SessionManager:
    clock: SimClock
    store_for: Callable[[str], HomeStore | None]
    new_home: Callable[[str], HomeConfig]
    sessions: dict[str, HomeSession] = field(default_factory=dict)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def get(self, uid: str) -> HomeSession:
        with self._lock:
            session = self.sessions.get(uid)
            if session is None:
                session = self._open(uid)
                self.sessions[uid] = session
            return session

    def add(self, uid: str, home: Home, store: HomeStore | None = None) -> HomeSession:
        """Register an already-built home (tests, single-home mode)."""
        session = self._wrap(uid, home, store, is_new=False)
        self.sessions[uid] = session
        return session

    def _open(self, uid: str) -> HomeSession:
        store = self.store_for(uid)
        config = store.load() if store else None
        is_new = config is None
        home = Home(config or self.new_home(uid), clock=self.clock)
        if store and not is_new:
            try:
                home.restore_activity(store.recent_activity(ACTIVITY_TO_LOAD))
            except Exception:
                # History is nice to have; never let it stop the home from opening.
                log.exception("Could not load activity history for %s", uid)
        return self._wrap(uid, home, store, is_new=is_new)

    def _wrap(self, uid: str, home: Home, store: HomeStore | None, *, is_new: bool) -> HomeSession:
        hub = Hub()
        home.subscribe(hub.publish)
        writer = None
        if store is not None:
            writer = StoreWriter(home, store)
            if is_new:
                store.save(home.to_config())
        if is_new:
            home.log("Welcome to Nestra", detail="Add your devices to get started")
        return HomeSession(uid, home, CommandProcessor(home), hub, writer)

    def tick(self, dt_minutes: float) -> None:
        for session in list(self.sessions.values()):
            session.home.tick(dt_minutes)

    def flush(self) -> None:
        for session in list(self.sessions.values()):
            if session.writer:
                session.writer.flush()
