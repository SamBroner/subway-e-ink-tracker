"""Phase A: the runner's decision logic is drivable with an injected clock and a
fake display — the foundation for the decision-trace tests.

These exercise the gate, the first-update, and the min-interval throttle with no
threads, no network, and no real rendering. They pin the current (transit-shaped)
behavior so later phases can move it onto the screen without changing it.
"""

from datetime import datetime, timedelta

import pytest

from data import AppData, BirdObservation, BirdResult, DataHub
from runner import Runner
from services.citibike_service import BikeAvailability
from services.subway_service import SubwayResult
from ui.display import DisplayIntent
from ui.screens import screen_manager


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

    def update(
        self,
        app_data=None,
        now=None,
        screen_name=None,
        partial=False,
        clear=False,
        intent=None,
    ):
        self.calls.append({
            "app_data": app_data,
            "partial": partial,
            "clear": clear,
            "intent": intent,
            "now": now,
            "screen_name": screen_name,
        })


class PrewarmingDisplay(RecordingDisplay):
    def __init__(self):
        super().__init__()
        self.prewarm_calls = []

    def prewarm(self, app_data, now, screen_names):
        self.prewarm_calls.append({
            "app_data": app_data,
            "now": now,
            "screen_names": screen_names,
        })


@pytest.fixture(autouse=True)
def reset_screen_manager():
    screen_manager.select(0)
    yield
    screen_manager.select(0)


def _ready_runner():
    clock = FakeClock()
    disp = RecordingDisplay()
    hub = DataHub(initial_data=AppData(
        weather={"current": {}},
        subway=SubwayResult(trains=[]),
        birds=_bird_result(),
    ))
    runner = Runner(display=disp, clock=clock, data_hub=hub)
    return runner, disp, clock


def _ready_prewarming_runner():
    clock = FakeClock()
    disp = PrewarmingDisplay()
    hub = DataHub(initial_data=AppData(
        weather={"current": {}},
        subway=SubwayResult(trains=[]),
        birds=_bird_result(),
    ))
    runner = Runner(display=disp, clock=clock, data_hub=hub)
    return runner, disp, clock


def _bike_availability() -> BikeAvailability:
    return BikeAvailability(
        classic_bikes=7,
        ebikes=2,
        station_id="station",
        station_name="Station",
    )


def _bird_result() -> BirdResult:
    return BirdResult(
        observations=[
            BirdObservation(
                sci_name="Poecile atricapillus",
                common_name="Black-capped Chickadee",
                count=4,
                last_seen="2026-06-11 22:40:10",
                max_confidence=0.908,
            )
        ],
        window_hours=24,
    )


def test_gate_blocks_without_data():
    disp = RecordingDisplay()
    runner = Runner(display=disp, clock=FakeClock(), data_hub=DataHub())
    # No weather/train data set yet -> the essential-data gate blocks rendering.
    runner._check_display_update()
    assert disp.calls == []


def test_first_update_renders():
    runner, disp, _ = _ready_runner()
    runner._check_display_update()
    assert len(disp.calls) == 1
    assert disp.calls[0]["screen_name"] == "transit"
    assert disp.calls[0]["app_data"].bikes is None
    assert disp.calls[0]["partial"] is False
    assert disp.calls[0]["clear"] is False
    assert disp.calls[0]["intent"] == DisplayIntent.SCREEN_TRANSITION


def test_runner_prewarms_remaining_screens_after_current_render():
    runner, disp, _ = _ready_prewarming_runner()

    runner._check_display_update()

    assert len(disp.prewarm_calls) == 1
    assert disp.prewarm_calls[0]["screen_names"] == [
        "bird-collage",
        "bird-collage-named",
        "birds",
        "bird-profile",
    ]


def test_runner_starts_touch_listener_when_enabled(monkeypatch):
    runner, _disp, _ = _ready_runner()
    touch_calls = []

    monkeypatch.setattr("runner.config.TOUCH_ENABLED", True)
    monkeypatch.setattr("runner.config.TOUCH_CHANNEL", 0)
    monkeypatch.setattr("runner.config.TOUCH_I2C_ADDRESS", 0x5A)
    monkeypatch.setattr("runner.start_spacebar_listener", lambda _callback: False)

    def fake_touch(callback, *, channel, address):
        touch_calls.append({
            "callback": callback,
            "channel": channel,
            "address": address,
        })
        return True

    monkeypatch.setattr("runner.start_touch_listener", fake_touch)

    runner._start_input_listeners()

    assert touch_calls == [{
        "callback": runner._advance_screen,
        "channel": 0,
        "address": 0x5A,
    }]


def test_runner_skips_touch_listener_when_disabled(monkeypatch):
    runner, _disp, _ = _ready_runner()
    touch_calls = []

    monkeypatch.setattr("runner.config.TOUCH_ENABLED", False)
    monkeypatch.setattr("runner.start_spacebar_listener", lambda _callback: False)
    monkeypatch.setattr("runner.start_touch_listener", lambda *_args, **_kwargs: touch_calls.append("touch"))

    runner._start_input_listeners()

    assert touch_calls == []


def test_min_interval_throttles():
    runner, disp, clock = _ready_runner()
    runner._check_display_update()        # first update renders
    runner._check_display_update()        # same instant -> throttled by min_interval
    assert len(disp.calls) == 1
    clock.advance(2)                      # past the 1s min_interval
    runner._check_display_update()
    assert len(disp.calls) == 2


def test_runner_passes_injected_now_to_display():
    runner, disp, clock = _ready_runner()
    runner._check_display_update()
    assert disp.calls[0]["now"] == clock.now()


def test_bike_update_alone_does_not_unblock_transit_but_is_kept():
    clock = FakeClock()
    disp = RecordingDisplay()
    hub = DataHub()
    runner = Runner(display=disp, clock=clock, data_hub=hub)
    bikes = _bike_availability()

    hub.handle_bike_update(bikes)
    assert disp.calls == []

    hub.handle_weather_update({"current": {}})
    assert disp.calls == []

    hub.handle_subway_update(SubwayResult(trains=[]))
    assert len(disp.calls) == 1
    assert disp.calls[0]["app_data"].bikes == bikes


def test_spacebar_advance_renders_bird_collage_without_transit_data():
    disp = RecordingDisplay()
    runner = Runner(
        display=disp,
        clock=FakeClock(),
        data_hub=DataHub(initial_data=AppData(birds=_bird_result())),
    )
    runner._advance_screen()
    assert disp.calls == [{
        "app_data": AppData(birds=_bird_result()),
        "partial": False,
        "clear": False,
        "intent": DisplayIntent.SCREEN_TRANSITION,
        "now": runner.clock.now(),
        "screen_name": "bird-collage",
    }]


def test_spacebar_advance_cycles_through_all_screens():
    runner, disp, _ = _ready_runner()

    for _ in range(screen_manager.count()):
        runner._advance_screen()

    assert [call["screen_name"] for call in disp.calls] == [
        "bird-collage",
        "bird-collage-named",
        "birds",
        "bird-profile",
        "transit",
    ]
    assert all(call["intent"] == DisplayIntent.SCREEN_TRANSITION for call in disp.calls)


def test_bird_collage_data_redraw_uses_full_refresh():
    runner, disp, clock = _ready_runner()
    screen_manager.select(1)  # bird-collage

    runner._check_display_update()
    clock.advance(2)
    runner.data_hub.handle_bird_update(BirdResult(
        observations=[
            BirdObservation(
                sci_name="Poecile atricapillus",
                common_name="Black-capped Chickadee",
                count=5,
                last_seen="2026-06-11 22:41:10",
                max_confidence=0.91,
            )
        ],
        window_hours=24,
    ))

    assert disp.calls[0]["screen_name"] == "bird-collage"
    assert disp.calls[0]["intent"] == DisplayIntent.SCREEN_TRANSITION
    assert disp.calls[1]["screen_name"] == "bird-collage"
    assert disp.calls[1]["clear"] is True
    assert disp.calls[1]["partial"] is False
    assert disp.calls[1]["intent"] == DisplayIntent.MAINTENANCE_CLEAR


def test_named_bird_collage_data_redraw_uses_full_refresh():
    runner, disp, clock = _ready_runner()
    screen_manager.select(2)  # bird-collage-named

    runner._check_display_update()
    clock.advance(2)
    runner.data_hub.handle_bird_update(BirdResult(
        observations=[
            BirdObservation(
                sci_name="Poecile atricapillus",
                common_name="Black-capped Chickadee",
                count=5,
                last_seen="2026-06-11 22:41:10",
                max_confidence=0.91,
            )
        ],
        window_hours=24,
    ))

    assert disp.calls[0]["screen_name"] == "bird-collage-named"
    assert disp.calls[1]["screen_name"] == "bird-collage-named"
    assert disp.calls[1]["clear"] is True
    assert disp.calls[1]["partial"] is False
    assert disp.calls[1]["intent"] == DisplayIntent.MAINTENANCE_CLEAR


def test_bird_list_screen_does_not_redraw_each_tick_when_data_unchanged():
    screen_manager.select(3)
    clock = FakeClock()
    disp = RecordingDisplay()
    runner = Runner(display=disp, clock=clock, data_hub=DataHub(initial_data=AppData(birds=_bird_result())))

    runner._check_display_update()
    clock.advance(2)
    runner._check_display_update()

    assert len(disp.calls) == 1
