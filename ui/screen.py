"""A screen: the ordered set of panes that fill the display.

`Screen.render` builds the blank frame, renders each pane into it, optionally
draws cross-pane chrome (e.g. section dividers) on top, and applies the 180°
rotation for the panel's physical orientation. Chrome is per-screen: a screen
with no dividers (e.g. a full-bleed hello screen) simply passes none.
"""

from typing import Callable, List, Optional

from PIL import Image, ImageDraw

from config.config import config
from ui.panes import Pane, RenderContext


class Screen:
    def __init__(self, panes: List[Pane], chrome: Optional[Callable[[ImageDraw.ImageDraw], None]] = None):
        self.panes = panes
        # Optional callable(draw) for cross-pane chrome, drawn on top of the panes.
        self.chrome = chrome

    def render(self, ctx: RenderContext) -> Image.Image:
        d = config.display
        img = Image.new('L', (d.WIDTH, d.HEIGHT), 255)
        draw = ImageDraw.Draw(img)

        # Panes first, then chrome on top — panes paste opaque tiles, so chrome
        # drawn last keeps the boundary dividers from being overwritten.
        for pane in self.panes:
            pane.render(img, ctx)
        if self.chrome is not None:
            self.chrome(draw)

        return img.rotate(180)
