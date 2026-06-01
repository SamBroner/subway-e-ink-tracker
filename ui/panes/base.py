"""Base types for panes: the render context, a per-pane drawing surface, and
the Pane base class.

Each pane renders into its own `w×h` tile through a `PaneSurface` whose
coordinate origin is the pane's top-left. Panes pass coordinates in global
(screen) space; the surface translates them by `-origin` and clips to the tile,
and `Screen` pastes the tile at the pane's rect. The clip makes the rect
authoritative: a pane cannot draw outside its own region.
"""

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


class PaneSurface:
    """A pane's drawing surface: a tile plus an origin offset.

    Mirrors the bits of PIL's ImageDraw / Image that panes use, translating
    global coordinates into tile-local ones. Drawing outside the tile is clipped
    by PIL — which is the point: content positioned by global coordinates cannot
    bleed past the pane's rect.
    """

    def __init__(self, tile: Image.Image, origin: tuple[int, int]):
        self._tile = tile
        self._draw = ImageDraw.Draw(tile)
        self._ox, self._oy = origin

    def _pt(self, xy):
        return (xy[0] - self._ox, xy[1] - self._oy)

    def _box(self, box):
        return (box[0] - self._ox, box[1] - self._oy, box[2] - self._ox, box[3] - self._oy)

    def text(self, xy, *args, **kwargs):
        self._draw.text(self._pt(xy), *args, **kwargs)

    def line(self, xy, *args, **kwargs):
        self._draw.line(self._box(xy), *args, **kwargs)

    def ellipse(self, xy, *args, **kwargs):
        self._draw.ellipse(self._box(xy), *args, **kwargs)

    def textbbox(self, xy, *args, **kwargs):
        # Callers use bbox widths (differences), which are translation-invariant.
        return self._draw.textbbox(self._pt(xy), *args, **kwargs)

    def textlength(self, *args, **kwargs):
        return self._draw.textlength(*args, **kwargs)

    def paste(self, im, box, mask=None):
        self._tile.paste(im, self._pt(box), mask)


class Pane:
    """A rectangular region of the screen that renders itself into a tile.

    The base exposes config shortcuts (self.display / weather / subway / time)
    so each pane's drawing code reads naturally. Subclasses implement ``paint``;
    the default ``render`` builds the tile, hands the pane a translating
    ``PaneSurface``, and pastes the result onto the frame.
    """

    def __init__(self, rect: tuple[int, int, int, int]):
        self.rect = rect  # (x, y, w, h) in screen space
        self.x, self.y, self.w, self.h = rect
        self.display = config.display
        self.weather = config.weather
        self.subway = config.subway
        self.time = config.time

    def render(self, img: Image.Image, ctx: RenderContext) -> None:
        tile = Image.new('L', (self.w, self.h), 255)
        surface = PaneSurface(tile, (self.x, self.y))
        self.paint(surface, ctx)
        img.paste(tile, (self.x, self.y))

    def paint(self, surface: PaneSurface, ctx: RenderContext) -> None:
        raise NotImplementedError
