"""Where a home's rooms and devices are saved.

`HomeStore` is the seam for Firebase: today `JsonFileStore` writes a local file;
a `FirestoreStore` with the same two methods will replace it once accounts are
added, with one stored home per user.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Protocol

from .simulator import Home
from .simulator.home import HomeConfig

# Events that mean the home's saved state changed. Environment ticks are not saved.
SAVE_EVENTS = {"device", "snapshot"}


class HomeStore(Protocol):
    def load(self) -> HomeConfig | None: ...

    def save(self, config: HomeConfig) -> None: ...


class JsonFileStore:
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


def attach(home: Home, store: HomeStore) -> None:
    """Save the home whenever its devices or structure change."""

    def on_event(message: dict) -> None:
        if message.get("type") in SAVE_EVENTS:
            store.save(home.to_config())

    home.subscribe(on_event)
