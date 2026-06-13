"""Panes that compose the display.

A `Pane` owns a rectangle of the screen and renders itself; the `Screen` is the
set of panes that tile the view (see `ui/screen.py`). Each pane lives in its own
module within this package; this `__init__` re-exports them as the public API so
callers can do `from ui.panes import SubwayPane` regardless of file layout.
"""

from ui.panes.base import Pane, RenderContext
from ui.panes.date import DatePane
from ui.panes.subway import SubwayPane
from ui.panes.hourly_weather import HourlyWeatherPane
from ui.panes.citibike import CitibikePane
from ui.panes.weather_overview import WeatherOverviewPane
from ui.panes.bird import BirdPane
from ui.panes.bird_collage import BirdCollagePane
from ui.panes.bird_profile import BirdProfilePane
from ui.panes.hello import HelloPane
from ui.panes.static_image import StaticImagePane

__all__ = [
    "Pane",
    "RenderContext",
    "DatePane",
    "SubwayPane",
    "HourlyWeatherPane",
    "CitibikePane",
    "WeatherOverviewPane",
    "BirdPane",
    "BirdCollagePane",
    "BirdProfilePane",
    "HelloPane",
    "StaticImagePane",
]
