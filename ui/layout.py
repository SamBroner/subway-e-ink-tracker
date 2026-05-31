from PIL import Image, ImageDraw
import logging
from datetime import datetime
from typing import List

import clock
from config.config import config
from ui.panes import (
    RenderContext,
    DatePane,
    SubwayPane,
    HourlyWeatherPane,
    CitibikePane,
    WeatherOverviewPane,
)
from ui.screen import Screen
from services.subway_service import TrainArrival
from services.citibike_service import BikeAvailability

logger = logging.getLogger(__name__)


class LayoutManager:
    """Vestigial holder kept only so the module-level ``layout_manager`` still
    exists for now. Chrome moved to Screen; per-pane drawing lives in ui/panes.py.
    """

    def __init__(self):
        self.display = config.display


# Create global layout manager instance
layout_manager = LayoutManager()


def _build_screen() -> Screen:
    """Compose the panes that tile the display, with rects from config."""
    d = config.display
    panes = [
        DatePane((0, 0, d.WIDTH, d.HEADER_HEIGHT)),
        SubwayPane((0, d.TRAIN_SECTION_Y, d.MAIN_SECTION_WIDTH, d.TRAIN_SECTION_HEIGHT)),
        HourlyWeatherPane((d.VERTICAL_LANE_X, d.TRAIN_SECTION_Y, d.VERTICAL_LANE_WIDTH, d.TRAIN_SECTION_HEIGHT)),
        CitibikePane((0, d.WEATHER_SECTION_Y, d.BOTTOM_VERTICAL_OFFSET, d.BOTTOM_SECTION_HEIGHT)),
        WeatherOverviewPane((d.BOTTOM_VERTICAL_OFFSET, d.WEATHER_SECTION_Y, d.WIDTH - d.BOTTOM_VERTICAL_OFFSET, d.BOTTOM_SECTION_HEIGHT)),
    ]
    return Screen(panes)


_screen = _build_screen()


# Provide single image creation function
def getImage(weather_data: dict, subway_data: List[TrainArrival], bike_data: BikeAvailability = None, now: datetime = None, subway_unavailable: bool = False) -> Image.Image:
    """Render the full display.

    Builds a per-frame RenderContext and delegates composition to the Screen.
    ``now`` defaults to clock.now() so production callers need not pass it;
    tests pass a fixed instant to render deterministically. ``subway_unavailable``
    distinguishes unreachable train feeds from an empty (but reachable) result.
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
    return _screen.render(ctx)
