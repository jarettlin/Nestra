import pytest

from nestra.commands import CommandProcessor
from nestra.simulator import Home, SimClock


@pytest.fixture
def home() -> Home:
    # Frozen at 14:00 so time-of-day rules are deterministic.
    return Home.from_file(clock=SimClock.at_hour(14))


@pytest.fixture
def processor(home: Home) -> CommandProcessor:
    return CommandProcessor(home)
