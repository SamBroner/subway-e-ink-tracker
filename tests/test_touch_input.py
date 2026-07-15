import builtins

import pytest

from ui.touch_input import TouchEdgeDetector, _run_touch_poll_loop, start_touch_listener


class FakeChannel:
    def __init__(self):
        self.value = False


class FakeSensor:
    def __init__(self):
        self.channels = [FakeChannel()]

    def __getitem__(self, index):
        return self.channels[index]


class FakeClock:
    def __init__(self):
        self.now = 10.0

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += seconds


def test_touch_detector_fires_on_rising_edge_only():
    sensor = FakeSensor()
    clock = FakeClock()
    calls = []
    detector = TouchEdgeDetector(
        sensor,
        channel=0,
        on_touch=lambda: calls.append("touch"),
        debounce_seconds=0.35,
        clock=clock,
    )

    detector.poll_once()
    sensor.channels[0].value = True
    detector.poll_once()
    detector.poll_once()
    clock.advance(1.0)
    detector.poll_once()

    assert calls == ["touch"]


def test_touch_detector_release_and_touch_again_advances_again():
    sensor = FakeSensor()
    clock = FakeClock()
    calls = []
    detector = TouchEdgeDetector(
        sensor,
        channel=0,
        on_touch=lambda: calls.append("touch"),
        debounce_seconds=0.35,
        clock=clock,
    )

    sensor.channels[0].value = True
    detector.poll_once()
    sensor.channels[0].value = False
    clock.advance(0.5)
    detector.poll_once()
    sensor.channels[0].value = True
    detector.poll_once()

    assert calls == ["touch", "touch"]


def test_touch_detector_debounces_fast_retouch():
    sensor = FakeSensor()
    clock = FakeClock()
    calls = []
    detector = TouchEdgeDetector(
        sensor,
        channel=0,
        on_touch=lambda: calls.append("touch"),
        debounce_seconds=0.35,
        clock=clock,
    )

    sensor.channels[0].value = True
    detector.poll_once()
    sensor.channels[0].value = False
    clock.advance(0.1)
    detector.poll_once()
    sensor.channels[0].value = True
    detector.poll_once()

    assert calls == ["touch"]


def test_start_touch_listener_missing_library_does_not_crash(monkeypatch):
    original_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "board":
            raise ImportError("no board module")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)

    assert not start_touch_listener(lambda: None)


def test_touch_poll_loop_continues_after_poll_error():
    class StopLoop(Exception):
        pass

    class FlakyDetector:
        def __init__(self):
            self.calls = 0

        def poll_once(self):
            self.calls += 1
            if self.calls == 1:
                raise OSError("i2c glitch")

    detector = FlakyDetector()

    def sleep(_seconds):
        if detector.calls >= 2:
            raise StopLoop

    with pytest.raises(StopLoop):
        _run_touch_poll_loop(detector, poll_interval_seconds=0, sleep=sleep)

    assert detector.calls == 2
