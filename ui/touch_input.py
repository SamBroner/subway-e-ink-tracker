"""Optional MPR121 capacitive-touch screen advancement."""

import logging
import threading
import time
from typing import Callable

from ui.key_input import Debouncer


logger = logging.getLogger(__name__)


class TouchEdgeDetector:
    """Detect rising touch edges on one MPR121 channel."""

    def __init__(
        self,
        sensor,
        *,
        channel: int,
        on_touch: Callable[[], None],
        debounce_seconds: float = 0.35,
        clock: Callable[[], float] = time.monotonic,
    ):
        self.sensor = sensor
        self.channel = channel
        self.on_touch = on_touch
        self.clock = clock
        self.debouncer = Debouncer(debounce_seconds)
        self._was_touched = False

    def poll_once(self) -> None:
        touched = bool(self.sensor[self.channel].value)
        if touched and not self._was_touched and self.debouncer.accept(self.clock()):
            try:
                self.on_touch()
            except Exception as e:
                logger.error("touch screen-switch handler error: %s", e)
        self._was_touched = touched


def start_touch_listener(
    on_touch: Callable[[], None],
    *,
    channel: int = 0,
    address: int = 0x5A,
    debounce_seconds: float = 0.35,
    poll_interval_seconds: float = 0.05,
) -> bool:
    """Start a daemon thread that calls ``on_touch`` on MPR121 rising edges.

    Returns True when the listener is active. Missing libraries, missing I2C,
    or sensor initialization failures are logged as warnings and return False
    so the display app can continue without touch input.
    """
    try:
        import board
        import busio
        import adafruit_mpr121

        i2c = busio.I2C(board.SCL, board.SDA)
        sensor = adafruit_mpr121.MPR121(i2c, address=address)
    except Exception as e:
        logger.warning("MPR121 touch input disabled: %s", e)
        return False

    detector = TouchEdgeDetector(
        sensor,
        channel=channel,
        on_touch=on_touch,
        debounce_seconds=debounce_seconds,
    )

    threading.Thread(
        target=_run_touch_poll_loop,
        args=(detector, poll_interval_seconds),
        daemon=True,
        name="mpr121-touch-listener",
    ).start()
    return True


def _run_touch_poll_loop(
    detector: TouchEdgeDetector,
    poll_interval_seconds: float,
    sleep: Callable[[float], None] = time.sleep,
) -> None:
    while True:
        try:
            detector.poll_once()
        except Exception as e:
            logger.warning("MPR121 touch poll failed; continuing: %s", e, exc_info=True)
        sleep(poll_interval_seconds)
