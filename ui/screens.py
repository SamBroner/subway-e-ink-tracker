"""Screen definitions and the active-screen manager.

A screen is a `Screen` (a set of panes that tile the view, plus optional chrome).
`ScreenManager` registers the available screens and tracks which one is active;
the runner advances the active screen in response to input.
"""

from typing import List, Optional, Tuple

from PIL import ImageDraw

from config.config import config
from ui.screen import Screen
from ui.panes import RenderContext
from services.subway_service import TrainArrival
from ui.panes import (
    DatePane,
    SubwayPane,
    HourlyWeatherPane,
    CitibikePane,
    WeatherOverviewPane,
    BirdPane,
    BirdCollagePane,
    BirdProfilePane,
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


def _displayed_time(ctx: RenderContext) -> str:
    return ctx.now.strftime("%I:%M:%S%p")


def _train_key(train: Optional[TrainArrival]) -> Optional[tuple[str, int]]:
    if train is None:
        return None
    return (train.train_id, train.minutes_until_arrival)


def _top_two_train_keys(ctx: RenderContext) -> tuple[Optional[tuple[str, int]], Optional[tuple[str, int]]]:
    subway = ctx.data.subway
    trains = subway.trains if subway else []
    return (
        _train_key(trains[0]) if len(trains) > 0 else None,
        _train_key(trains[1]) if len(trains) > 1 else None,
    )


def _transit_redraw_key(ctx: RenderContext) -> tuple:
    subway = ctx.data.subway
    return (
        _displayed_time(ctx),
        _top_two_train_keys(ctx),
        subway.service_unavailable if subway else False,
    )


def _transit_should_redraw(ctx: RenderContext, prev_ctx: Optional[RenderContext]) -> bool:
    if prev_ctx is None:
        return True
    return _transit_redraw_key(ctx) != _transit_redraw_key(prev_ctx)


def _bird_redraw_key(ctx: RenderContext) -> tuple:
    birds = ctx.data.birds
    if birds is None:
        return (None,)
    return (
        birds.window_hours,
        birds.source_unavailable,
        tuple(
            (
                obs.sci_name,
                obs.common_name,
                obs.count,
                obs.last_seen,
                obs.max_confidence,
            )
            for obs in birds.observations
        ),
    )


def _birds_should_redraw(ctx: RenderContext, prev_ctx: Optional[RenderContext]) -> bool:
    if prev_ctx is None:
        return True
    return _bird_redraw_key(ctx) != _bird_redraw_key(prev_ctx)


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
    return Screen(
        panes,
        chrome=_draw_transit_chrome,
        required_data={"weather", "subway"},
        redraw_policy=_transit_should_redraw,
    )


def build_birds_screen() -> Screen:
    """A full-screen data-backed BirdNET observations screen."""
    d = config.display
    return Screen(
        [BirdPane((0, 0, d.WIDTH, d.HEIGHT))],
        required_data={"birds"},
        redraw_policy=_birds_should_redraw,
    )


def build_bird_collage_screen() -> Screen:
    """A full-screen unlabeled collage of recent BirdNET observations."""
    d = config.display
    return Screen(
        [BirdCollagePane((0, 0, d.WIDTH, d.HEIGHT))],
        required_data={"birds"},
        redraw_policy=_birds_should_redraw,
    )


def build_named_bird_collage_screen() -> Screen:
    """A full-screen named collage of recent BirdNET observations."""
    d = config.display
    return Screen(
        [BirdCollagePane((0, 0, d.WIDTH, d.HEIGHT), named=True)],
        required_data={"birds"},
        redraw_policy=_birds_should_redraw,
    )


def build_bird_profile_screen() -> Screen:
    """A full-screen profile for the most recent BirdNET observation."""
    d = config.display
    return Screen(
        [BirdProfilePane((0, 0, d.WIDTH, d.HEIGHT))],
        required_data={"birds"},
        redraw_policy=_birds_should_redraw,
    )


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

    def advance(self) -> bool:
        """Advance to the next registered screen; returns True if the active screen changed."""
        if len(self._screens) <= 1:
            return False
        self._index = (self._index + 1) % len(self._screens)
        return True

# Registered screens, in order. Spacebar advances through this order.
# The first is the default/active at startup.
screen_manager = ScreenManager([
    ("transit", build_transit_screen()),
    ("bird-collage", build_bird_collage_screen()),
    ("bird-collage-named", build_named_bird_collage_screen()),
    ("birds", build_birds_screen()),
    ("bird-profile", build_bird_profile_screen()),
])
