import logging
import csv
import os
import sys
from time import sleep
import traceback
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from PIL import Image, ImageChops
from pathlib import Path
from typing import Optional
import threading
import time

from data.models import AppData
from ui.layout import getImageFromAppData
from config.config import config

logger = logging.getLogger(__name__)

# Only import IT8951 on Raspberry Pi
IS_RASPBERRY_PI = sys.platform == 'linux'
if IS_RASPBERRY_PI:
    from IT8951.display import AutoEPDDisplay # type: ignore
    from IT8951 import constants # type: ignore


class DisplayIntent(Enum):
    NORMAL = "normal"
    SCREEN_TRANSITION = "screen_transition"
    MAINTENANCE_CLEAR = "maintenance_clear"


@dataclass
class DisplayFrame:
    image: Image.Image
    partial: bool
    clear: bool
    screen_name: Optional[str]
    render_requested_at: Optional[datetime]
    queued_at: float
    sequence: int
    displayed_clock: str
    intent: DisplayIntent = DisplayIntent.NORMAL
    overwritten_before_consume: int = 0


def _bool_env(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.lower() in {"1", "true", "yes", "on"}


def _timestamp(value: float) -> str:
    return datetime.fromtimestamp(value).isoformat(timespec="microseconds")


def _safe_filename_part(value: str) -> str:
    safe = "".join(c if c.isalnum() else "-" for c in value.strip())
    return "-".join(part for part in safe.split("-") if part) or "unknown"


def _displayed_clock(now: Optional[datetime]) -> str:
    if now is None:
        return ""
    return now.strftime("%I:%M:%S%p").lstrip("0").lower()


def _coerce_intent(intent: DisplayIntent | str | None, clear: bool) -> DisplayIntent:
    if intent is None:
        return DisplayIntent.MAINTENANCE_CLEAR if clear else DisplayIntent.NORMAL
    if isinstance(intent, DisplayIntent):
        return intent
    return DisplayIntent(intent)


class DebugDisplay:
    def __init__(self, output_dir: Path | str = "debug_output", history_enabled: Optional[bool] = None):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(exist_ok=True)
        self.current_image_path = self.output_dir / "current_display.png"
        self.history_enabled = (
            _bool_env("DEBUG_FRAME_HISTORY")
            if history_enabled is None
            else history_enabled
        )
        self.history_dir = self.output_dir / "frames"
        self.manifest_path = self.output_dir / "frame_manifest.csv"
        if self.history_enabled:
            self.history_dir.mkdir(exist_ok=True)
    
    def initialize(self):
        """Initialize the debug display"""
        logger.info("Initialized debug display - images will be saved to debug_output/current_display.png")
        if self.history_enabled:
            logger.info(
                "Debug frame history enabled - timestamped frames will be saved to %s",
                self.history_dir,
            )
        
    def update(
        self,
        img: Image.Image,
        partial: bool = False,
        clear: bool = False,
        metadata: DisplayFrame | None = None,
    ):
        """Update the debug display with new data"""
        try:
            self._update_display(img, metadata)
                
        except Exception as e:
            logger.error(f"Error updating debug display: {str(e)}")
            raise

    def _update_display(self, img: Image.Image, metadata: DisplayFrame | None = None):
        """Save the image without automatically opening it"""
        try:
            img = img.rotate(180)
            img.save(self.current_image_path)
            logger.info(f"Saved display image to {self.current_image_path}")
            if self.history_enabled:
                self._save_history_frame(img, metadata)
                
        except Exception as e:
            logger.error(f"Error updating debug display: {str(e)}")
            raise

    def _save_history_frame(self, img: Image.Image, metadata: DisplayFrame | None):
        consumed_at = time.time()
        sequence = metadata.sequence if metadata else 0
        screen_name = metadata.screen_name if metadata and metadata.screen_name else "unknown"
        clock = metadata.displayed_clock if metadata else ""
        filename = (
            f"{sequence:06d}_"
            f"{datetime.fromtimestamp(consumed_at).strftime('%Y%m%d-%H%M%S-%f')}_"
            f"{_safe_filename_part(screen_name)}"
        )
        if clock:
            filename += f"_{_safe_filename_part(clock)}"
        frame_path = self.history_dir / f"{filename}.png"
        img.save(frame_path)
        self._append_manifest(frame_path, consumed_at, metadata)

    def _append_manifest(self, frame_path: Path, consumed_at: float, metadata: DisplayFrame | None):
        fieldnames = [
            "sequence",
            "frame_path",
            "screen_name",
            "displayed_clock",
            "intent",
            "partial",
            "clear",
            "render_requested_at",
            "queued_at",
            "consumed_at",
            "queue_wait_seconds",
            "overwritten_before_consume",
        ]
        row = {
            "sequence": metadata.sequence if metadata else "",
            "frame_path": str(frame_path),
            "screen_name": metadata.screen_name if metadata else "",
            "displayed_clock": metadata.displayed_clock if metadata else "",
            "intent": metadata.intent.value if metadata else "",
            "partial": metadata.partial if metadata else "",
            "clear": metadata.clear if metadata else "",
            "render_requested_at": (
                metadata.render_requested_at.isoformat(timespec="microseconds")
                if metadata and metadata.render_requested_at
                else ""
            ),
            "queued_at": _timestamp(metadata.queued_at) if metadata else "",
            "consumed_at": _timestamp(consumed_at),
            "queue_wait_seconds": (
                f"{consumed_at - metadata.queued_at:.6f}" if metadata else ""
            ),
            "overwritten_before_consume": metadata.overwritten_before_consume if metadata else "",
        }
        write_header = not self.manifest_path.exists()
        with self.manifest_path.open("a", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            if write_header:
                writer.writeheader()
            writer.writerow(row)

class EInkDisplay:
    def __init__(self):
        if IS_RASPBERRY_PI:
            self.display = AutoEPDDisplay(vcom=-2.06, rotate='CCW', spi_hz=12000000)
            logger.info(f"VCOM set to {self.display.epd.get_vcom()}")
        else:
            raise RuntimeError("EInkDisplay can only be used on Raspberry Pi")
        
        self.previous_image = None
    
    def initialize(self):
        """Initialize the e-ink display"""
        pass

    def _clear_display(self):
        """Clear the e-ink display"""
        try:
            logger.info("Clearing display")
            self.display.frame_buf.paste(0xFF, box=(0, 0, config.display.WIDTH, config.display.HEIGHT))
            self.display.draw_full(constants.DisplayModes.GC16)
            logger.info("Display cleared")
            
        except Exception as e:
            logger.error(f"Error clearing display: {str(e)}")
            raise

    def restart(self):
        logger.error("Likely Error: Restarting display")

        self.display.epd.sleep()
        sleep(2)
        self.display = AutoEPDDisplay(vcom=-2.06, rotate='CCW', spi_hz=12000000)
        sleep(2)
        logger.error("Display restarted")
    
    def _update_display(
        self,
        img: Image.Image,
        clear: bool = False,
        intent: DisplayIntent = DisplayIntent.NORMAL,
    ):
        """Update the e-ink display using IT8951"""
        try:
            if intent in {DisplayIntent.SCREEN_TRANSITION, DisplayIntent.MAINTENANCE_CLEAR} or clear:
                waveform = constants.DisplayModes.GLR16
            else:
                waveform = constants.DisplayModes.DU

            start = time.monotonic()
            logger.info("Sending image to display (waveform=%s, intent=%s)", waveform, intent.value)
            self.display.frame_buf.paste(img)
            self.display.draw_full(waveform)
            duration = time.monotonic() - start
            logger.info(
                "Display update complete (duration=%.3fs, waveform=%s, intent=%s)",
                duration,
                waveform,
                intent.value,
            )
            
        except Exception as e:
            print(f"Error updating display: {str(e)}")
            self.display.epd.wait_display_ready()
            logger.error(f"Error updating display: {str(e)}")
            raise

    def _update_partial_display(self, img: Image.Image, box: tuple):
        """Update a portion of the e-ink display using IT8951"""
        try:
            start = time.monotonic()
            logger.info("Sending partial image to display (box=%s)", box)
            self.display.frame_buf.paste(img.crop(box), box)
            self.display.draw_partial(constants.DisplayModes.DU) # .DU is faster but has ghosting
            duration = time.monotonic() - start
            logger.info("Partial display update complete (duration=%.3fs, box=%s)", duration, box)
            
        except Exception as e:
            print(f"Error updating partial display: {str(e)}")
            self.display.epd.wait_display_ready()
            # self.restart()

            logger.error(f"Error updating partial display: {str(e)}")
            raise

    def _get_diff_box(self, img1: Image.Image, img2: Image.Image) -> tuple:
        """Get bounding box of differences between two images"""
        diff = ImageChops.difference(img1, img2)
        return diff.getbbox()

    def update(
        self,
        img: Image.Image,
        partial: bool = False,
        clear: bool = False,
        metadata: DisplayFrame | None = None,
    ):
        """Update the e-ink display with new data
        ToDo: I'm hiding logic here that only does a partial refresh on small changes rather than plumbing all the way through.
        """
        try:
            if metadata is not None:
                logger.info(
                    "Consuming display frame sequence=%s screen=%s clock=%s intent=%s queue_wait=%.3fs overwritten=%s partial=%s clear=%s",
                    metadata.sequence,
                    metadata.screen_name,
                    metadata.displayed_clock,
                    metadata.intent.value,
                    time.time() - metadata.queued_at,
                    metadata.overwritten_before_consume,
                    partial,
                    clear,
                )
            intent = metadata.intent if metadata else DisplayIntent.MAINTENANCE_CLEAR if clear else DisplayIntent.NORMAL
            if intent in {DisplayIntent.SCREEN_TRANSITION, DisplayIntent.MAINTENANCE_CLEAR}:
                self._update_display(img, clear, intent)
                self.previous_image = img
                return

            if self.previous_image:
                diff_box = self._get_diff_box(self.previous_image, img)
            else:
                diff_box = None

            # Nothing changed since the last frame (and not an explicit clear):
            # skip the repaint, so a static screen doesn't full-refresh every tick.
            # (Checked before the large-diff escalation below, which also nulls diff_box.)
            if self.previous_image and diff_box is None and not clear:
                logger.info("Skipping e-ink update; frame is identical to previous image")
                return

            # Fix - maybe have the partial boolean parameter be tuple of max width/height"
            if diff_box and (diff_box[2] - diff_box[0] > 50 or diff_box[3] - diff_box[1] > 50):
                logger.info("Large diff detected, doing full update")
                diff_box = None

            if partial and diff_box:
                self._update_partial_display(img, diff_box)
            else:
                self._update_display(img, clear, intent)
            
            self.previous_image = img
                
        except Exception as e:
            logger.error(f"Error updating display: {str(e)}")
            logger.error(traceback.format_exc())
            raise

class Display:
    def __init__(self):
        self.display = None
        self.next_frame = None
        self.clear_cooldown_seconds = config.timing.DISPLAY_CLEAR_COOLDOWN_SECONDS
        self._large_update_cooldown_until = 0
        self._queue_lock = threading.Lock()
        self._frame_sequence = 0
        self._pending_overwrite_count = 0
        self.update_thread = threading.Thread(target=self._process_queue)
        self.update_thread.daemon = True
        self.update_thread.start()
    
    def initialize(self):
        """Initialize the appropriate display based on config"""
        if config.DEBUG:
            self.display = DebugDisplay()
        elif IS_RASPBERRY_PI:
            self.display = EInkDisplay()
            self.display._clear_display()
        else:
            raise RuntimeError("Cannot initialize e-ink display on non-Raspberry Pi device when not in debug mode")
        
        self.display.initialize()

    def _process_queue(self):
        """Process the latest img, ensuring only one update per second"""
        while True:
            try:
                now = time.time()
                frame = self._take_next_frame(now)

                if frame is not None:
                    self.display.update(frame.image, frame.partial, frame.clear, frame)
                    if self._starts_large_update_cooldown(frame):
                        with self._queue_lock:
                            self._large_update_cooldown_until = time.time() + self.clear_cooldown_seconds
                time.sleep(1)  # Ensure only one update per second
            except Exception as e:
                logger.error(f"Error processing update queue: {str(e)}")
                logger.error(traceback.format_exc())

    def _take_next_frame(self, now: float) -> DisplayFrame | None:
        with self._queue_lock:
            if self.next_frame is None:
                return None
            if (
                self.next_frame.intent == DisplayIntent.NORMAL
                and now < self._large_update_cooldown_until
            ):
                return None

            frame = self.next_frame
            self.next_frame = None
            frame.overwritten_before_consume = self._pending_overwrite_count
            self._pending_overwrite_count = 0
            return frame

    def _starts_large_update_cooldown(self, frame: DisplayFrame) -> bool:
        return frame.intent in {
            DisplayIntent.SCREEN_TRANSITION,
            DisplayIntent.MAINTENANCE_CLEAR,
        }

    def update(
        self,
        app_data: AppData,
        now: Optional[datetime] = None,
        screen_name: Optional[str] = None,
        partial: bool = False,
        clear: bool = False,
        intent: DisplayIntent | str | None = None,
    ):
        """Queue an update for the display with new data"""
        try:
            logger.info("Generating display image...")
            display_intent = _coerce_intent(intent, clear)
            img = getImageFromAppData(
                app_data,
                now=now,
                screen_name=screen_name,
            )
            queued_at = time.time()
            with self._queue_lock:
                self._frame_sequence += 1
                frame = DisplayFrame(
                    image=img,
                    partial=partial,
                    clear=clear,
                    screen_name=screen_name,
                    render_requested_at=now,
                    queued_at=queued_at,
                    sequence=self._frame_sequence,
                    displayed_clock=_displayed_clock(now),
                    intent=display_intent,
                )
                if self.next_frame is not None:
                    self._pending_overwrite_count += 1
                    logger.info(
                        "Replacing queued display frame with sequence=%s (pending_overwrites=%s)",
                        frame.sequence,
                        self._pending_overwrite_count,
                    )
                self.next_frame = frame
                
        except Exception as e:
            logger.error(f"Error queuing display update: {str(e)}")
            logger.error(traceback.format_exc())
            raise
