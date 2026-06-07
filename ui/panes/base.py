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

from PIL import Image, ImageDraw

from config.config import config
from data.models import AppData


@dataclass
class RenderContext:
    """Everything a pane might need for one frame, built once per render."""
    data: AppData
    now: datetime


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

    def _translate_points(self, xy):
        # ImageDraw.line accepts either a flat (x0, y0, x1, y1, ...) sequence or
        # a list of (x, y) points; translate both forms by the origin.
        if xy and isinstance(xy[0], (tuple, list)):
            return [(x - self._ox, y - self._oy) for x, y in xy]
        return tuple(c - (self._ox if i % 2 == 0 else self._oy) for i, c in enumerate(xy))

    def text(self, xy, *args, **kwargs):
        self._draw.text(self._pt(xy), *args, **kwargs)

    def line(self, xy, *args, **kwargs):
        self._draw.line(self._translate_points(xy), *args, **kwargs)

    def ellipse(self, xy, *args, **kwargs):
        self._draw.ellipse(self._box(xy), *args, **kwargs)

    def textbbox(self, xy, *args, **kwargs):
        # Callers use bbox widths (differences), which are translation-invariant.
        return self._draw.textbbox(self._pt(xy), *args, **kwargs)

    def textlength(self, *args, **kwargs):
        return self._draw.textlength(*args, **kwargs)

    def paste(self, im, xy, mask=None):
        # `mask` is typically the source image's own alpha — icons paste with
        # themselves as the mask.
        self._tile.paste(im, self._pt(xy), mask)


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
