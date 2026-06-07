from datetime import datetime
from typing import List, Optional

from PIL import Image

import clock
from ui.panes import RenderContext
from ui.screens import screen_manager
from services.subway_service import TrainArrival
from services.citibike_service import BikeAvailability


# Provide single image creation function
def getImage(weather_data: dict, subway_data: List[TrainArrival], bike_data: BikeAvailability = None,
             now: datetime = None, subway_unavailable: bool = False,
             screen_name: Optional[str] = None) -> Image.Image:
    """Render the active screen (or a named one) to a display-ready image.

    Builds a per-frame RenderContext shared by every pane. ``now`` defaults to
    clock.now() so production callers need not pass it; tests pass a fixed instant.
    ``screen_name`` forces a specific registered screen (used by tests); otherwise
    the ScreenManager's current screen is rendered, so runtime screen switches are
    reflected here.
    """
    if now is None:
        now = clock.now()
    ctx = RenderContext(
        weather=weather_data,
        trains=subway_data,
        bikes=bike_data,
        now=now,
        subway_unavailable=subway_unavailable,
    )
    screen = screen_manager.get(screen_name) if screen_name else screen_manager.current()
    return screen.render(ctx)
