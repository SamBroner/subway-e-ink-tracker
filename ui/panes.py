"""Panes that compose the display.

A `Pane` owns a rectangle of the screen and knows how to render itself. The
screen is the set of panes that tile the view. See `ui/screen.py`.

Step 1.a (this commit) keeps every pane a *thin wrapper*: its `render` just
delegates to the existing `LayoutManager._draw_*` method, which still holds the
drawing logic and reads absolute config coordinates. The deferred
`from ui.layout import layout_manager` inside each `render` avoids a circular
import (ui.layout imports this module). Both the delegation and the deferred
import go away in step 1.b, when each pane's drawing code is relocated here.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional

from PIL import Image, ImageDraw

from services.subway_service import TrainArrival
from services.citibike_service import BikeAvailability


@dataclass
class RenderContext:
    """Everything a pane might need for one frame, built once per render."""
    weather: dict
    trains: List[TrainArrival]
    bikes: Optional[BikeAvailability]
    now: datetime
    subway_unavailable: bool = False


class Pane:
    """A rectangular region of the screen that renders itself."""

    def __init__(self, rect: tuple[int, int, int, int]):
        self.rect = rect  # (x, y, w, h) in screen space

    def render(self, img: Image.Image, draw: ImageDraw.ImageDraw, ctx: RenderContext) -> None:
        raise NotImplementedError


class DatePane(Pane):
    """Header: date and current time."""
    def render(self, img, draw, ctx):
        from ui.layout import layout_manager
        layout_manager._draw_time(draw, ctx.now)


class SubwayPane(Pane):
    """Train section: F/G arrivals, no-trains notice, or service-unavailable."""
    def render(self, img, draw, ctx):
        from ui.layout import layout_manager
        layout_manager._draw_subway_info(draw, ctx.trains, ctx.now, ctx.subway_unavailable)


class HourlyWeatherPane(Pane):
    """Right lane: the next 12 hours of forecast."""
    def render(self, img, draw, ctx):
        from ui.layout import layout_manager
        layout_manager._draw_vertical_lane(img, draw, ctx.weather, ctx.now)


class CitibikePane(Pane):
    """Bottom-left: classic and e-bike counts."""
    def render(self, img, draw, ctx):
        from ui.layout import layout_manager
        layout_manager._draw_bike_panel(img, draw, ctx.bikes)


class WeatherOverviewPane(Pane):
    """Bottom-right: enlarged current conditions, high/low, wind, precip."""
    def render(self, img, draw, ctx):
        from ui.layout import layout_manager
        layout_manager._draw_weather_overview(img, draw, ctx.weather, ctx.now)
