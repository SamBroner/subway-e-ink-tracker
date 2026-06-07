"""Phase A: the runner's decision logic is drivable with an injected clock and a
fake display — the foundation for the decision-trace tests.

These exercise the gate, the first-update, and the min-interval throttle with no
threads, no network, and no real rendering. They pin the current (transit-shaped)
behavior so later phases can move it onto the screen without changing it.
"""

from datetime import datetime, timedelta

from runner import Runner


class FakeClock:
    """Deterministic, advanceable stand-in for the runner's Clock."""

    def __init__(self):
        self._t = 1000.0
        self._dt = datetime(2026, 1, 15, 14, 23, 0)  # minute 23 -> no hourly clear

    def time(self) -> float:
        return self._t

    def now(self) -> datetime:
        return self._dt

    def advance(self, seconds: float):
        self._t += seconds
        self._dt += timedelta(seconds=seconds)


class RecordingDisplay:
    """Records each update() call instead of rendering/driving a panel."""

    def __init__(self):
        self.calls = []

    def initialize(self):
        pass

    def update(self, weather_data=None, train_data=None, bike_data=None,
               subway_unavailable=False, partial=False, clear=False):
        self.calls.append({"partial": partial, "clear": clear})


def _ready_runner():
    clock = FakeClock()
    disp = RecordingDisplay()
    runner = Runner(display=disp, clock=clock)
    runner.state.weather_data = {"current": {}}  # truthy -> passes the data gate
    runner.state.train_data = []                 # not None -> passes the data gate
    return runner, disp, clock


def test_gate_blocks_without_data():
    disp = RecordingDisplay()
    runner = Runner(display=disp, clock=FakeClock())
    # No weather/train data set yet -> the essential-data gate blocks rendering.
    runner._check_display_update()
    assert disp.calls == []


def test_first_update_renders():
    runner, disp, _ = _ready_runner()
    runner._check_display_update()
    assert len(disp.calls) == 1


def test_min_interval_throttles():
    runner, disp, clock = _ready_runner()
    runner._check_display_update()        # first update renders
    runner._check_display_update()        # same instant -> throttled by min_interval
    assert len(disp.calls) == 1
    clock.advance(2)                      # past the 1s min_interval
    runner._check_display_update()
    assert len(disp.calls) == 2
