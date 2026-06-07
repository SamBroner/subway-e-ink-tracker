"""Single-keypress stdin reader for interactive screen switching.

When a terminal is attached, reads one character at a time (no Enter needed) and
invokes a callback for digit keys. When there is no tty (e.g. running as a
systemd service), it no-ops, so it is safe to start unconditionally.
"""

import atexit
import logging
import select
import sys
import threading
from typing import Callable

logger = logging.getLogger(__name__)


def start_digit_listener(on_digit: Callable[[int], None]) -> bool:
    """Start a daemon thread that calls ``on_digit(n)`` for each digit key pressed.

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
        tty.setcbreak(fd)
        while True:
            ready, _, _ = select.select([sys.stdin], [], [], 0.5)
            if not ready:
                continue
            ch = sys.stdin.read(1)
            if ch and ch.isdigit():
                try:
                    on_digit(int(ch))
                except Exception as e:
                    logger.error(f"screen-switch handler error: {e}")

    threading.Thread(target=_loop, daemon=True, name="key-listener").start()
    return True
