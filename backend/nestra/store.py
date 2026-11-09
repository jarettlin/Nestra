"""Where each home's rooms, devices and activity history are saved.

  JsonFileStore   a local JSON file (development, no login)
  FirestoreStore  Firestore document homes/{uid}, with history in
                  homes/{uid}/activity/{entry}

Writes happen on a background thread so a slow network never stalls the
dashboard; bursts of changes (dragging a slider) collapse into one save.
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Protocol

from .simulator import Home
from .simulator.home import ActivityEntry, HomeConfig

log = logging.getLogger("nestra.store")

# Events that mean the home's saved state changed. Environment ticks are not saved.
SAVE_EVENTS = {"device", "snapshot"}


class HomeStore(Protocol):
    def load(self) -> HomeConfig | None: ...

    def save(self, config: HomeConfig) -> None: ...

    def append_activity(self, entry: ActivityEntry) -> None: ...

    def recent_activity(self, limit: int) -> list[ActivityEntry]: ...


class JsonFileStore:
    """Saves the home to one JSON file. Activity history isn't kept across restarts."""

    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)

    def load(self) -> HomeConfig | None:
        if not self.path.exists():
            return None
        return HomeConfig.model_validate_json(self.path.read_text())

    def save(self, config: HomeConfig) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        data = json.dumps(config.model_dump(mode="json"), indent=2)
        # Write to a temp file then rename, so a crash never leaves a half-written file.
        fd, tmp = tempfile.mkstemp(dir=self.path.parent, prefix=".home-", suffix=".json")
        try:
            with os.fdopen(fd, "w") as f:
                f.write(data)
            os.replace(tmp, self.path)
        except BaseException:
            Path(tmp).unlink(missing_ok=True)
            raise

    def append_activity(self, entry: ActivityEntry) -> None:
        pass

    def recent_activity(self, limit: int) -> list[ActivityEntry]:
        return []


class FirestoreStore:
    """One document per user: homes/{uid}. Only the backend (admin SDK) reads it;
    firestore.rules denies direct access from apps."""

    def __init__(self, client: Any, uid: str) -> None:
        self.doc = client.collection("homes").document(uid)

    def load(self) -> HomeConfig | None:
        snap = self.doc.get()
        if not snap.exists:
            return None
        data = snap.to_dict() or {}
        data.pop("updated_at", None)
        return HomeConfig.model_validate(data)

    def save(self, config: HomeConfig) -> None:
        from google.cloud.firestore import SERVER_TIMESTAMP

        self.doc.set({**config.model_dump(mode="json"), "updated_at": SERVER_TIMESTAMP})

    def append_activity(self, entry: ActivityEntry) -> None:
        # Sortable id: time then sequence number, e.g. "2026-11-09T19:42:00-000042".
        doc_id = f"{entry.time}-{entry.id:06d}"
        self.doc.collection("activity").document(doc_id).set(entry.model_dump(mode="json"))

    def recent_activity(self, limit: int) -> list[ActivityEntry]:
        from google.cloud.firestore import Query

        # Sort on the entry's own "time" field: Firestore indexes ordinary fields
        # automatically in both directions, so newest-first needs no custom index
        # (sorting on the document id descending would).
        query = self.doc.collection("activity").order_by("time", direction=Query.DESCENDING).limit(limit)
        entries = [ActivityEntry.model_validate(s.to_dict()) for s in query.stream()]
        return sorted(entries, key=lambda e: (e.time, e.id), reverse=True)


class StoreWriter:
    """Saves a home in the background whenever it changes."""

    def __init__(self, home: Home, store: HomeStore) -> None:
        self.home = home
        self.store = store
        self._pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="nestra-store")
        self._lock = threading.Lock()
        self._pending: HomeConfig | None = None
        home.subscribe(self._on_event)

    def _on_event(self, message: dict) -> None:
        kind = message.get("type")
        if kind in SAVE_EVENTS:
            with self._lock:
                schedule = self._pending is None
                # Snapshot now, on the event thread, so the save is consistent.
                self._pending = self.home.to_config().model_copy(deep=True)
            if schedule:
                self._pool.submit(self._save_latest)
        elif kind == "activity":
            entry = ActivityEntry.model_validate(message["data"])
            self._pool.submit(self._safely, self.store.append_activity, entry)

    def _save_latest(self) -> None:
        with self._lock:
            config, self._pending = self._pending, None
        if config is not None:
            self._safely(self.store.save, config)

    @staticmethod
    def _safely(fn, *args) -> None:
        try:
            fn(*args)
        except Exception:
            log.exception("Saving to the store failed")

    def flush(self) -> None:
        """Wait for pending writes (used on shutdown and in tests)."""
        self._pool.submit(lambda: None).result()
