import csv
import threading
import time
from datetime import datetime

from PIL import Image

from data import AppData
from ui import display as display_module
from ui.display import DebugDisplay, Display, DisplayFrame, DisplayIntent


def _image():
    return Image.new("L", (8, 8), 255)


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
        screen_name="hello",
        intent=DisplayIntent.SCREEN_TRANSITION,
    )
    frame = display._take_next_frame(now)

    assert frame is not None
    assert frame.intent == DisplayIntent.SCREEN_TRANSITION
    assert display.next_frame is None


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


def _display_without_thread():
    display = Display.__new__(Display)
    display.next_frame = None
    display.clear_cooldown_seconds = 5
    display._large_update_cooldown_until = 0
    display._queue_lock = threading.Lock()
    display._frame_sequence = 0
    display._pending_overwrite_count = 0
    return display
