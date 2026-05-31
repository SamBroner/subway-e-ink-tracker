"""Canonical time source for the app.

Rendering and any time-of-day logic should read 'now' from here (or accept it
as an injected parameter that defaults to here) so that behaviour is a pure
function of its inputs and can be frozen deterministically in tests.

Note: this returns a tz-aware America/New_York datetime. Services that do
arithmetic against naive datetimes (e.g. nyct-gtfs arrival times in
subway_service) should not be switched to this without reconciling tz-awareness.
"""

from datetime import datetime
import pytz

NY_TZ = pytz.timezone("America/New_York")


def now() -> datetime:
    """Current time as a tz-aware America/New_York datetime."""
    return datetime.now(NY_TZ)
