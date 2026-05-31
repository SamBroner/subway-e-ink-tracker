"""Base types for panes: the render context and the Pane base class."""

from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional

from PIL import Image, ImageDraw

from config.config import config
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
    """A rectangular region of the screen that renders itself.

    The base carries the same config shortcuts the old LayoutManager exposed
    (self.display / weather / subway / time) so each pane's drawing code reads
    naturally.
    """

    def __init__(self, rect: tuple[int, int, int, int]):
        self.rect = rect  # (x, y, w, h) in screen space
        self.display = config.display
        self.weather = config.weather
        self.subway = config.subway
        self.time = config.time

    def render(self, img: Image.Image, draw: ImageDraw.ImageDraw, ctx: RenderContext) -> None:
        raise NotImplementedError
