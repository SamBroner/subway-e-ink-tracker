"""Screen definitions and the active-screen manager.

A screen is a `Screen` (a set of panes that tile the view, plus optional chrome).
`ScreenManager` registers the available screens and tracks which one is active;
the runner switches the active screen in response to input (number keys today).
"""

from typing import List, Tuple

from PIL import ImageDraw

from config.config import config
from ui.screen import Screen
from ui.panes import (
    DatePane,
    SubwayPane,
    HourlyWeatherPane,
    CitibikePane,
    WeatherOverviewPane,
    HelloPane,
)


def _draw_transit_chrome(draw: ImageDraw.ImageDraw) -> None:
    """Section dividers for the transit screen."""
    d = config.display
    # Header / train divider
    draw.line((0, d.HEADER_HEIGHT, d.WIDTH, d.HEADER_HEIGHT), fill=0)
    # Train / bottom divider (full width)
    bottom_divider_y = d.TRAIN_SECTION_Y + d.TRAIN_SECTION_HEIGHT
    draw.line((0, bottom_divider_y, d.WIDTH, bottom_divider_y), fill=0)
    # Vertical line for the right (hourly) lane
    draw.line((d.VERTICAL_LANE_X, d.HEADER_HEIGHT,
               d.VERTICAL_LANE_X, d.TRAIN_SECTION_Y + d.TRAIN_SECTION_HEIGHT), fill=0)
    # Vertical line splitting the bottom section (bikes | weather)
    bottom_vertical_x = d.BOTTOM_VERTICAL_OFFSET
    draw.line((bottom_vertical_x, bottom_divider_y, bottom_vertical_x, d.HEIGHT), fill=0)


def build_transit_screen() -> Screen:
    """The default screen: date, F/G arrivals, hourly weather, bikes, current weather."""
    d = config.display
    panes = [
        DatePane((0, 0, d.WIDTH, d.HEADER_HEIGHT)),
        SubwayPane((0, d.TRAIN_SECTION_Y, d.MAIN_SECTION_WIDTH, d.TRAIN_SECTION_HEIGHT)),
        HourlyWeatherPane((d.VERTICAL_LANE_X, d.TRAIN_SECTION_Y, d.VERTICAL_LANE_WIDTH, d.TRAIN_SECTION_HEIGHT)),
        CitibikePane((0, d.WEATHER_SECTION_Y, d.BOTTOM_VERTICAL_OFFSET, d.BOTTOM_SECTION_HEIGHT)),
        WeatherOverviewPane((d.BOTTOM_VERTICAL_OFFSET, d.WEATHER_SECTION_Y, d.WIDTH - d.BOTTOM_VERTICAL_OFFSET, d.BOTTOM_SECTION_HEIGHT)),
    ]
    return Screen(panes, chrome=_draw_transit_chrome)


def build_hello_screen() -> Screen:
    """A minimal full-bleed screen for experimentation (no chrome)."""
    d = config.display
    return Screen([HelloPane((0, 0, d.WIDTH, d.HEIGHT))])


class ScreenManager:
    """Holds the registered screens and the active selection."""

    def __init__(self, screens: List[Tuple[str, Screen]]):
        self._screens = screens
        self._index = 0

    def current(self) -> Screen:
        return self._screens[self._index][1]

    def current_name(self) -> str:
        return self._screens[self._index][0]

    def names(self) -> List[str]:
        return [name for name, _ in self._screens]

    def count(self) -> int:
        return len(self._screens)

    def get(self, name: str) -> Screen:
        for n, screen in self._screens:
            if n == name:
                return screen
        raise KeyError(f"No screen named {name!r}; have {self.names()}")

    def select(self, index: int) -> bool:
        """Activate a screen by 0-based index; returns True if the active screen changed."""
        if 0 <= index < len(self._screens):
            changed = index != self._index
            self._index = index
            return changed
        return False


# Registered screens, in order. Number keys map 1-based to this order
# (1 -> transit, 2 -> hello). The first is the default/active at startup.
screen_manager = ScreenManager([
    ("transit", build_transit_screen()),
    ("hello", build_hello_screen()),
])
