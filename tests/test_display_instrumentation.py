import csv
import threading
import time
from datetime import datetime

from PIL import Image

from data import AppData
from ui import display as display_module
from ui.display import DebugDisplay, Display, DisplayFrame, DisplayIntent, EInkDisplay
from ui.render_cache import RenderCache


def _image():
    return Image.new("L", (8, 8), 255)


def test_eink_maintenance_clear_blanks_panel_before_grayscale_redraw():
    eink = EInkDisplay.__new__(EInkDisplay)
    eink.previous_image = None
    calls = []
    eink._clear_display = lambda: calls.append(("clear",))
    eink._update_display = lambda image, clear, intent: calls.append(
        ("draw", image, clear, intent)
    )
    image = _image()

    eink.update(image, clear=True)

    assert calls == [
        ("clear",),
        ("draw", image, False, DisplayIntent.MAINTENANCE_CLEAR),
    ]
    assert eink.previous_image is image


def test_eink_screen_transition_redraws_without_hard_clear():
    eink = EInkDisplay.__new__(EInkDisplay)
    eink.previous_image = None
    calls = []
    eink._clear_display = lambda: calls.append(("clear",))
    eink._update_display = lambda image, clear, intent: calls.append(
        ("draw", image, clear, intent)
    )
    image = _image()
    metadata = DisplayFrame(
        image=image,
        partial=False,
        clear=False,
        screen_name="all-in-one",
        render_requested_at=datetime(2026, 1, 15, 14, 23, 5),
        queued_at=time.time(),
        sequence=1,
        displayed_clock="2:23:05pm",
        intent=DisplayIntent.SCREEN_TRANSITION,
    )

    eink.update(image, metadata=metadata)

    assert calls == [
        ("draw", image, False, DisplayIntent.SCREEN_TRANSITION),
    ]
    assert eink.previous_image is image


def test_debug_display_history_writes_timestamped_frame_and_manifest(tmp_path):
    debug = DebugDisplay(output_dir=tmp_path, history_enabled=True)
    queued_at = time.time()
    metadata = DisplayFrame(
        image=_image(),
        partial=True,
        clear=False,
        screen_name="transit",
        render_requested_at=datetime(2026, 1, 15, 14, 23, 5),
        queued_at=queued_at,
        sequence=7,
        displayed_clock="2:23:05pm",
        overwritten_before_consume=3,
    )

    debug.update(_image(), partial=True, clear=False, metadata=metadata)

    assert (tmp_path / "current_display.png").exists()
    history_files = list((tmp_path / "frames").glob("*.png"))
    assert len(history_files) == 1
    assert "000007" in history_files[0].name
    assert "transit" in history_files[0].name

    with (tmp_path / "frame_manifest.csv").open() as f:
        rows = list(csv.DictReader(f))

    assert rows == [{
        "sequence": "7",
        "frame_path": str(history_files[0]),
        "screen_name": "transit",
        "displayed_clock": "2:23:05pm",
        "intent": "normal",
        "partial": "True",
        "clear": "False",
        "render_requested_at": "2026-01-15T14:23:05.000000",
        "queued_at": rows[0]["queued_at"],
        "consumed_at": rows[0]["consumed_at"],
        "queue_wait_seconds": rows[0]["queue_wait_seconds"],
        "overwritten_before_consume": "3",
    }]


def test_debug_display_rotates_manifest_when_existing_schema_is_stale(tmp_path):
    old_manifest = tmp_path / "frame_manifest.csv"
    old_contents = "sequence,frame_path\n1,old.png\n"
    old_manifest.write_text(old_contents)

    debug = DebugDisplay(output_dir=tmp_path, history_enabled=True)
    metadata = DisplayFrame(
        image=_image(),
        partial=False,
        clear=False,
        screen_name="bird-collage",
        render_requested_at=datetime(2026, 1, 15, 14, 23, 5),
        queued_at=time.time(),
        sequence=8,
        displayed_clock="2:23:05pm",
    )

    debug.update(_image(), metadata=metadata)

    rotated = list(tmp_path.glob("frame_manifest.*.csv"))
    assert len(rotated) == 1
    assert rotated[0].read_text() == old_contents

    with old_manifest.open() as f:
        rows = list(csv.DictReader(f))

    assert rows[0]["sequence"] == "8"
    assert rows[0]["screen_name"] == "bird-collage"
    assert rows[0]["intent"] == "normal"


def test_display_queue_records_overwritten_frames(monkeypatch):
    display = _display_without_thread()

    monkeypatch.setattr(
        display_module,
        "getImageFromAppData",
        lambda app_data, now=None, screen_name=None: _image(),
    )

    display.update(AppData(), now=datetime(2026, 1, 15, 14, 23, 1), screen_name="transit")
    display.update(AppData(), now=datetime(2026, 1, 15, 14, 23, 2), screen_name="transit")

    frame = display._take_next_frame(time.time())

    assert frame is not None
    assert frame.sequence == 2
    assert frame.displayed_clock == "2:23:02pm"
    assert frame.overwritten_before_consume == 1
    assert display.next_frame is None
    assert display._pending_overwrite_count == 0


def test_display_queue_delays_normal_frames_during_large_update_cooldown(monkeypatch):
    display = _display_without_thread()
    now = time.time()
    display._large_update_cooldown_until = now + 5

    monkeypatch.setattr(
        display_module,
        "getImageFromAppData",
        lambda app_data, now=None, screen_name=None: _image(),
    )

    display.update(AppData(), now=datetime(2026, 1, 15, 14, 23, 1), screen_name="transit")

    assert display._take_next_frame(now) is None
    assert display.next_frame is not None

    frame = display._take_next_frame(now + 6)

    assert frame is not None
    assert frame.intent == DisplayIntent.NORMAL
    assert display.next_frame is None


def test_display_queue_allows_screen_transitions_during_large_update_cooldown(monkeypatch):
    display = _display_without_thread()
    now = time.time()
    display._large_update_cooldown_until = now + 5

    monkeypatch.setattr(
        display_module,
        "getImageFromAppData",
        lambda app_data, now=None, screen_name=None: _image(),
    )

    display.update(
        AppData(),
        now=datetime(2026, 1, 15, 14, 23, 1),
        screen_name="bird-collage",
        intent=DisplayIntent.SCREEN_TRANSITION,
    )
    frame = display._take_next_frame(now)

    assert frame is not None
    assert frame.intent == DisplayIntent.SCREEN_TRANSITION
    assert display.next_frame is None


def test_normal_frame_does_not_replace_pending_screen_transition(monkeypatch):
    display = _display_without_thread()
    render_calls = []

    def fake_render(app_data, now=None, screen_name=None):
        render_calls.append(screen_name)
        return _image()

    monkeypatch.setattr(display_module, "getImageFromAppData", fake_render)

    display.update(
        AppData(),
        now=datetime(2026, 1, 15, 14, 23, 1),
        screen_name="bird-collage",
        intent=DisplayIntent.SCREEN_TRANSITION,
    )
    display.update(
        AppData(),
        now=datetime(2026, 1, 15, 14, 23, 2),
        screen_name="transit",
        intent=DisplayIntent.NORMAL,
    )
    frame = display._take_next_frame(time.time())

    assert frame is not None
    assert frame.screen_name == "bird-collage"
    assert frame.intent == DisplayIntent.SCREEN_TRANSITION
    assert render_calls == ["bird-collage"]


def test_screen_transition_replaces_pending_normal_frame(monkeypatch):
    display = _display_without_thread()

    monkeypatch.setattr(
        display_module,
        "getImageFromAppData",
        lambda app_data, now=None, screen_name=None: _image(),
    )

    display.update(
        AppData(),
        now=datetime(2026, 1, 15, 14, 23, 1),
        screen_name="transit",
        intent=DisplayIntent.NORMAL,
    )
    display.update(
        AppData(),
        now=datetime(2026, 1, 15, 14, 23, 2),
        screen_name="bird-collage",
        intent=DisplayIntent.SCREEN_TRANSITION,
    )
    frame = display._take_next_frame(time.time())

    assert frame is not None
    assert frame.screen_name == "bird-collage"
    assert frame.intent == DisplayIntent.SCREEN_TRANSITION
    assert frame.overwritten_before_consume == 1


def test_legacy_clear_frames_map_to_maintenance_clear(monkeypatch):
    display = _display_without_thread()

    monkeypatch.setattr(
        display_module,
        "getImageFromAppData",
        lambda app_data, now=None, screen_name=None: _image(),
    )

    display.update(AppData(), clear=True)
    frame = display._take_next_frame(time.time())

    assert frame is not None
    assert frame.intent == DisplayIntent.MAINTENANCE_CLEAR


def test_display_reuses_cached_render_for_same_screen_key(monkeypatch):
    display = _display_without_thread()
    render_calls = []

    def fake_render(app_data, now=None, screen_name=None):
        render_calls.append((screen_name, now))
        return _image()

    monkeypatch.setattr(display_module, "getImageFromAppData", fake_render)

    now = datetime(2026, 1, 15, 14, 23, 1)
    display.update(AppData(), now=now, screen_name="birds")
    display.update(AppData(), now=now, screen_name="birds")

    assert render_calls == [("birds", now)]


def test_bird_screen_cache_survives_clock_second_changes(monkeypatch):
    display = _display_without_thread()
    render_calls = []

    def fake_render(app_data, now=None, screen_name=None):
        render_calls.append((screen_name, now))
        return _image()

    monkeypatch.setattr(display_module, "getImageFromAppData", fake_render)

    display.update(AppData(), now=datetime(2026, 1, 15, 14, 23, 1), screen_name="bird-collage")
    display.update(AppData(), now=datetime(2026, 1, 15, 14, 23, 2), screen_name="bird-collage")

    assert len(render_calls) == 1


def test_normal_transit_frames_do_not_use_cache(monkeypatch):
    display = _display_without_thread()
    render_calls = []

    def fake_render(app_data, now=None, screen_name=None):
        render_calls.append((screen_name, now))
        return _image()

    monkeypatch.setattr(display_module, "getImageFromAppData", fake_render)

    display.update(AppData(), now=datetime(2026, 1, 15, 14, 23, 1), screen_name="transit")
    display.update(AppData(), now=datetime(2026, 1, 15, 14, 23, 1), screen_name="transit")

    assert len(render_calls) == 2


def test_display_prewarms_screens_sequentially(monkeypatch):
    display = _display_without_thread()
    render_calls = []

    def fake_render(app_data, now=None, screen_name=None):
        render_calls.append(screen_name)
        return _image()

    monkeypatch.setattr(display_module, "getImageFromAppData", fake_render)

    display.prewarm(
        AppData(),
        datetime(2026, 1, 15, 14, 23, 1),
        ["bird-collage", "bird-collage-named", "birds"],
    )

    assert display.render_cache.wait_for_idle()
    assert render_calls == ["bird-collage", "bird-collage-named", "birds"]


def test_foreground_render_reuses_inflight_prewarm_result():
    cache = RenderCache()
    entered_render = threading.Event()
    release_render = threading.Event()
    render_calls = []
    results = []

    def fake_render(app_data, now=None, screen_name=None):
        render_calls.append(screen_name)
        entered_render.set()
        assert release_render.wait(1)
        return _image()

    app_data = AppData()
    now = datetime(2026, 1, 15, 14, 23, 1)
    cache.prewarm(app_data, now, ["birds"], fake_render)
    assert entered_render.wait(1)

    foreground = threading.Thread(
        target=lambda: results.append(cache.get_or_render(app_data, now, "birds", fake_render))
    )
    foreground.start()
    time.sleep(0.05)

    assert foreground.is_alive()
    release_render.set()
    foreground.join(1)

    assert not foreground.is_alive()
    assert cache.wait_for_idle()
    assert len(results) == 1
    assert render_calls == ["birds"]


def _display_without_thread():
    display = Display.__new__(Display)
    display.render_cache = RenderCache()
    display.next_frame = None
    display.clear_cooldown_seconds = 5
    display._large_update_cooldown_until = 0
    display._queue_lock = threading.Lock()
    display._queue_ready = threading.Condition(display._queue_lock)
    display._frame_sequence = 0
    display._pending_overwrite_count = 0
    return display
