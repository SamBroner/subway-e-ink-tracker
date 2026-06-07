"""Single-keypress stdin reader for interactive screen advancement.

When a terminal is attached, reads one character at a time (no Enter needed) and
invokes a callback for the spacebar. When there is no tty (e.g. running as a
systemd service), it no-ops, so it is safe to start unconditionally.
"""

import atexit
import logging
import select
import sys
import threading
import time
from typing import Callable

logger = logging.getLogger(__name__)


class Debouncer:
    def __init__(self, interval_seconds: float):
        self.interval_seconds = interval_seconds
        self._last_accepted_at: float | None = None

    def accept(self, now: float) -> bool:
        if (
            self._last_accepted_at is not None
            and now - self._last_accepted_at < self.interval_seconds
        ):
            return False
        self._last_accepted_at = now
        return True


def start_spacebar_listener(on_space: Callable[[], None], debounce_seconds: float = 0.25) -> bool:
    """Start a daemon thread that calls ``on_space()`` for each spacebar press.

    Returns True if a listener was started (a tty is attached), else False.
    """
    if not getattr(sys, "stdin", None) or not sys.stdin.isatty():
        logger.info("No tty attached; keyboard screen-switching disabled.")
        return False

    import termios
    import tty

    fd = sys.stdin.fileno()
    old_attrs = termios.tcgetattr(fd)
    atexit.register(lambda: termios.tcsetattr(fd, termios.TCSADRAIN, old_attrs))

    def _loop():
        # cbreak (not raw): single-key reads, but Ctrl-C/SIGINT still work.
        debouncer = Debouncer(debounce_seconds)
        tty.setcbreak(fd)
        while True:
            ready, _, _ = select.select([sys.stdin], [], [], 0.5)
            if not ready:
                continue
            ch = sys.stdin.read(1)
            if ch == " " and debouncer.accept(time.monotonic()):
                try:
                    on_space()
                except Exception as e:
                    logger.error(f"screen-switch handler error: {e}")

    threading.Thread(target=_loop, daemon=True, name="spacebar-listener").start()
    return True
