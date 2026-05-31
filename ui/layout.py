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
    """Holds the cross-pane chrome (the section dividers).

    Per-pane drawing now lives in ui/panes.py; this draws what spans panes.
    """

    def __init__(self):
        self.display = config.display

    def _draw_sections(self, draw: ImageDraw.ImageDraw):
        """Draw the section dividing lines"""
        # Line between header and train section
        draw.line((0, self.display.HEADER_HEIGHT,
                   self.display.WIDTH, self.display.HEADER_HEIGHT), fill=0)

        # Line between train and weather section - now full width
        bottom_divider_y = self.display.TRAIN_SECTION_Y + self.display.TRAIN_SECTION_HEIGHT
        draw.line((0, bottom_divider_y,
                   self.display.WIDTH, bottom_divider_y), fill=0)

        # Vertical line for the right lane
        draw.line((self.display.VERTICAL_LANE_X, self.display.HEADER_HEIGHT,
                   self.display.VERTICAL_LANE_X, self.display.TRAIN_SECTION_Y + self.display.TRAIN_SECTION_HEIGHT), fill=0)

        # Additional vertical line in bottom section (mirror offset)
        bottom_vertical_x = self.display.BOTTOM_VERTICAL_OFFSET
        draw.line(
            (bottom_vertical_x, bottom_divider_y, bottom_vertical_x, self.display.HEIGHT),
            fill=0
        )


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
    return Screen(panes, chrome_fn=layout_manager._draw_sections)


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
