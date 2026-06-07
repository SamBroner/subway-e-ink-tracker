from datetime import datetime
from typing import List, Optional

from PIL import Image

import clock
from config.config import config
from data.models import AppData
from ui.panes import RenderContext
from ui.screens import screen_manager
from services.subway_service import TrainArrival
from services.subway_service import SubwayResult
from services.citibike_service import BikeAvailability


def getImageFromAppData(app_data: AppData, now: datetime = None,
                        screen_name: Optional[str] = None) -> Image.Image:
    """Render a screen from the typed app-data snapshot."""
    if now is None:
        now = clock.now()
    ctx = RenderContext(data=app_data, now=now)
    screen = screen_manager.get(screen_name) if screen_name else screen_manager.current()
    return screen.render(ctx)


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
    unavailable_lines = (
        frozenset({config.TRAIN_LINE_1, config.TRAIN_LINE_2})
        if subway_unavailable
        else frozenset()
    )
    app_data = AppData(
        weather=weather_data,
        subway=SubwayResult(trains=subway_data or [], unavailable_lines=unavailable_lines),
        bikes=bike_data,
    )
    return getImageFromAppData(app_data, now=now, screen_name=screen_name)
