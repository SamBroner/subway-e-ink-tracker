"""Clock text shared by render keys, screen policies, and debug metadata."""

from datetime import datetime
from typing import Optional


def displayed_clock(now: Optional[datetime], *, compact: bool = False) -> str:
    if now is None:
        return ""
    text = now.strftime("%I:%M:%S%p")
    return text.lstrip("0").lower() if compact else text
