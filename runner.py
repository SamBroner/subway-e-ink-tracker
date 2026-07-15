# Now import other modules
import os
from datetime import datetime
import time
from typing import Optional
from dataclasses import dataclass
from data import AppData, DataHub, DataKey
from config.config import config
from ui.display import Display, DisplayIntent
from ui.panes import RenderContext
from ui.screens import screen_manager
from ui.key_input import start_spacebar_listener
from ui.touch_input import start_touch_listener
import logging
import logging.handlers

# Set up logging configuration
log_file = 'log.txt'
max_bytes = 5 * 1024 * 1024  # 5MB max file size

# Configure logging based on environment
quiet_mode = os.getenv('QUIET_MODE', 'false').lower() == 'true'
log_level = logging.WARNING if quiet_mode else logging.DEBUG

# Ensure log directory exists
try:
    logging.basicConfig(
        level=log_level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.handlers.RotatingFileHandler(
                log_file,
                maxBytes=max_bytes,
                backupCount=5
            ),
            logging.StreamHandler() if not quiet_mode else logging.NullHandler()
        ],
        force=True
    )
except Exception as e:
    print(f"Error setting up logging: {str(e)}")
    raise

logger = logging.getLogger(__name__)

@dataclass
class DisplayState:
    last_display_update: float = 0
    last_display_clear: float = 0


class Clock:
    """Time source for the runner's scheduling; injectable so tests can drive the
    decision logic deterministically. The real clock preserves prior behavior
    exactly: time.time() for intervals, datetime.now() for the hourly check.
    """
    def time(self) -> float:
        return time.time()

    def now(self) -> datetime:
        return datetime.now()


class Runner:
    def __init__(self, display=None, clock: "Clock" = None, data_hub: DataHub = None):
        logger.info("Initializing Runner")
        self.display = display if display is not None else Display()
        self.clock = clock if clock is not None else Clock()
        self.data_hub = data_hub if data_hub is not None else DataHub()
        self.state = DisplayState()
        self.min_interval = config.timing.DISPLAY_MIN_INTERVAL_SECONDS
        self._previous_render_ctx: Optional[RenderContext] = None
        self._previous_screen_name: Optional[str] = None
        self.data_hub.subscribe(self.handle_data_update)

    def handle_data_update(self, key: DataKey, data: AppData):
        """Handle a new source snapshot from the data hub."""
        if key == "subway" and data.subway is not None:
            now = self.clock.now()
            trains = data.subway.trains
            logger.info("-" * 40)
            logger.info(f"Train update at {now.strftime('%Y-%m-%d %H:%M:%S')}")
            logger.info(
                f"Number of trains: {len(trains)} "
                f"(service_unavailable={data.subway.service_unavailable})"
            )

            for train in trains:
                logger.debug(f"Train: {train.arrival_time} ({train.minutes_until_arrival} min)")
        elif key == "bikes" and data.bikes is not None:
            logger.info(f"Bike update: {data.bikes.classic_bikes} classic, {data.bikes.ebikes} ebikes")
        elif key == "birds" and data.birds is not None:
            logger.info(
                "Bird update: %s observations over %sh (source_unavailable=%s)",
                len(data.birds.observations),
                data.birds.window_hours,
                data.birds.source_unavailable,
            )

        self._check_display_update(force=False)
    
    def _build_render_context(self) -> RenderContext:
        return RenderContext(
            data=self.data_hub.data,
            now=self.clock.now(),
        )

    def _missing_required_data(self, data: AppData) -> list[DataKey]:
        required = screen_manager.current().requires()
        return [key for key in required if not data.has(key)]

    def _check_display_update(
        self,
        force: bool = False,
        clear: bool = False,
        intent: DisplayIntent | None = None,
    ):
        """Check if we should update the display"""
        now = self.clock.time()
        screen = screen_manager.current()
        screen_name = screen_manager.current_name()
        ctx = self._build_render_context()

        missing = self._missing_required_data(ctx.data)
        if missing:
            logger.debug(
                "[DISPLAY SKIP] Missing data for %s screen: %s",
                screen_name,
                ", ".join(missing),
            )
            return

        # Warn if bike data hasn't arrived yet (but don't block display)
        if screen_name == "transit" and not ctx.data.has("bikes"):
            logger.warning("[DISPLAY] Bike data not available, displaying without it")

        # Always update if this is our first update
        if self.state.last_display_update == 0:
            logger.info("[DISPLAY UPDATE] First update")
            first_update_intent = intent or DisplayIntent.SCREEN_TRANSITION
            self._update_display(clear=clear, ctx=ctx, intent=first_update_intent)
            return

        # If forced (screen switch/manual clean redraw), update immediately
        if force:
            logger.info("[DISPLAY UPDATE] Forced update")
            self._update_display(clear=clear, ctx=ctx, intent=intent)
            return

        # Clear the display at the top of every hour (aligned to clock time)
        current_time = self.clock.now()
        if (current_time.minute == 0) and (now - self.state.last_display_clear >= 3500):
            logger.info("[DISPLAY UPDATE] Hourly clear")
            self._update_display(clear=True, ctx=ctx, intent=DisplayIntent.MAINTENANCE_CLEAR)
            return

        prev_ctx = self._previous_render_ctx if self._previous_screen_name == screen_name else None
        if not screen.should_redraw(ctx, prev_ctx):
            logger.debug("[DISPLAY SKIP] %s screen does not need redraw", screen_name)
            return

        # Respect the minimum interval for regular ticks/data events.
        time_since_update = now - self.state.last_display_update

        if time_since_update >= self.min_interval:
            logger.info(
                f"[DISPLAY UPDATE] {screen_name} redraw ({time_since_update:.1f}s >= {self.min_interval}s)"
            )
            if screen.profile.full_refresh_on_redraw:
                self._update_display(
                    clear=True,
                    ctx=ctx,
                    intent=DisplayIntent.MAINTENANCE_CLEAR,
                )
            else:
                self._update_display(ctx=ctx)
            return
        else:
            logger.debug(f"[DISPLAY SKIP] Min interval not met ({time_since_update:.1f}s < {self.min_interval}s)")
    
    def _update_display(
        self,
        clear: bool = False,
        ctx: Optional[RenderContext] = None,
        intent: DisplayIntent | None = None,
    ):
        """Update the display with current state"""
        try:
            if ctx is None:
                ctx = self._build_render_context()

            display_intent = intent or (
                DisplayIntent.MAINTENANCE_CLEAR if clear else DisplayIntent.NORMAL
            )
            partial = display_intent == DisplayIntent.NORMAL and not clear
            screen_name = screen_manager.current_name()

            queued = self.display.update(
                app_data=ctx.data,
                now=ctx.now,
                screen_name=screen_name,
                partial=partial,
                clear=clear,
                intent=display_intent,
            )
            if queued is not False:
                self._prewarm_screen_renders(ctx, screen_name)
            else:
                return

            if (clear == True):
                self.state.last_display_clear = self.clock.time()

            self.state.last_display_update = self.clock.time()
            self._previous_render_ctx = ctx
            self._previous_screen_name = screen_name
        except Exception as e:
            logger.error(f"Error updating display: {str(e)}")

    def _prewarm_screen_renders(self, ctx: RenderContext, current_screen_name: str) -> None:
        prewarm = getattr(self.display, "prewarm", None)
        if prewarm is None:
            return

        screen_names = self._prewarm_screen_order(current_screen_name, ctx.data)
        if not screen_names:
            return
        prewarm(ctx.data, ctx.now, screen_names)

    def _prewarm_screen_order(self, current_screen_name: str, data: AppData) -> list[str]:
        names = screen_manager.names()
        if current_screen_name not in names:
            return []

        current_index = names.index(current_screen_name)
        ordered = names[current_index + 1:] + names[:current_index]
        return [
            name
            for name in ordered
            if name != "transit" and self._screen_has_required_data(name, data)
        ]

    def _screen_has_required_data(self, screen_name: str, data: AppData) -> bool:
        required = screen_manager.get(screen_name).requires()
        return all(data.has(key) for key in required)

    def _advance_screen(self):
        """Advance to the next registered screen and force a transition redraw."""
        if screen_manager.advance():
            logger.info(f"Advanced to screen {screen_manager.current_name()}")
            self._previous_render_ctx = None
            self._previous_screen_name = None
            self._check_display_update(
                force=True,
                intent=DisplayIntent.SCREEN_TRANSITION,
            )

    def _start_input_listeners(self) -> None:
        # Interactive screen switching: press space to advance screens.
        # No-ops when there's no tty (e.g. running as a systemd service).
        if start_spacebar_listener(self._advance_screen):
            logger.info(
                "Screen switching enabled: press Space to cycle screens (%s)",
                ", ".join(screen_manager.names()),
            )
        if config.TOUCH_ENABLED and start_touch_listener(
            self._advance_screen,
            channel=config.TOUCH_CHANNEL,
            address=config.TOUCH_I2C_ADDRESS,
        ):
            logger.info(
                "MPR121 touch screen switching enabled on channel %s at address 0x%02x",
                config.TOUCH_CHANNEL,
                config.TOUCH_I2C_ADDRESS,
            )

    def run(self):
        """Main run method"""
        try:
            logger.info("Starting services...")
            
            # Initialize display
            self.display.initialize()

            # Subscribe to and start all data feeds.
            self.data_hub.start()

            self._start_input_listeners()

            # Keep the main thread running
            try:
                while True:
                    time.sleep(1)
                    self._check_display_update()
            except KeyboardInterrupt:
                logger.info("Shutting down...")
                
        except Exception as e:
            logger.error(f"Error in main runner: {str(e)}")
        finally:
            # Clean shutdown
            self.data_hub.stop()

if __name__ == "__main__":
    runner = Runner()
    runner.run()
