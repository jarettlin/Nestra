from __future__ import annotations

import time
from datetime import datetime, timedelta


class SimClock:
    """Simulated wall clock.

    `scale` is how many simulated seconds pass per real second: 1 is real time,
    60 makes a simulated minute pass every real second, and 0 freezes the clock
    (handy for tests and for tuning fuzzy rules at a fixed time of day).
    """

    def __init__(self, start: datetime | None = None, scale: float = 1.0) -> None:
        self._start = start or datetime.now()
        self._t0 = time.monotonic()
        self.scale = scale

    def now(self) -> datetime:
        elapsed = (time.monotonic() - self._t0) * self.scale
        return self._start + timedelta(seconds=elapsed)

    def hour(self) -> float:
        """Time of day as fractional hours, 0.0 to 24.0."""
        n = self.now()
        return n.hour + n.minute / 60 + n.second / 3600

    @classmethod
    def at_hour(cls, hour: float, scale: float = 0.0) -> SimClock:
        """Clock starting today at `hour` (fractional hours allowed)."""
        midnight = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        return cls(start=midnight + timedelta(hours=hour), scale=scale)
