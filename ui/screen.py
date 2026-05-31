"""A screen: the ordered set of panes that fill the display.

`Screen.render` builds the blank frame, draws the chrome (section dividers),
renders each pane, and applies the 180° rotation for the panel's physical
orientation — i.e. it replaces the body of the old `LayoutManager.create_image`.
"""

from typing import Callable, List, Optional

from PIL import Image, ImageDraw

from config.config import config
from ui.panes import Pane, RenderContext


class Screen:
    def __init__(self, panes: List[Pane], chrome_fn: Optional[Callable[[ImageDraw.ImageDraw], None]] = None):
        self.panes = panes
        # chrome_fn draws cross-pane chrome (the dividers). In step 1.a it points
        # at LayoutManager._draw_sections; step 2 moves that logic onto the Screen.
        self.chrome_fn = chrome_fn

    def render(self, ctx: RenderContext) -> Image.Image:
        d = config.display
        img = Image.new('L', (d.WIDTH, d.HEIGHT), 255)
        draw = ImageDraw.Draw(img)

        # Chrome first, then panes — preserving the original draw order so the
        # output is pixel-identical to the previous create_image.
        if self.chrome_fn is not None:
            self.chrome_fn(draw)
        for pane in self.panes:
            pane.render(img, draw, ctx)

        return img.rotate(180)
