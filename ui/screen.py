"""A screen: the ordered set of panes that fill the display.

`Screen.render` builds the blank frame, draws the chrome (the section dividers
that span panes), renders each pane, and applies the 180° rotation for the
panel's physical orientation — i.e. it replaces the body of the old
`LayoutManager.create_image`.
"""

from typing import List

from PIL import Image, ImageDraw

from config.config import config
from ui.panes import Pane, RenderContext


class Screen:
    def __init__(self, panes: List[Pane]):
        self.panes = panes

    def render(self, ctx: RenderContext) -> Image.Image:
        d = config.display
        img = Image.new('L', (d.WIDTH, d.HEIGHT), 255)
        draw = ImageDraw.Draw(img)

        # Panes first, then chrome on top. Panes paste opaque tiles (Approach A),
        # so chrome must be drawn last or the dividers at pane boundaries would
        # be overwritten.
        for pane in self.panes:
            pane.render(img, draw, ctx)
        self._draw_chrome(draw)

        return img.rotate(180)

    def _draw_chrome(self, draw: ImageDraw.ImageDraw) -> None:
        """Draw the section dividers that separate the panes."""
        d = config.display

        # Line between header and train section
        draw.line((0, d.HEADER_HEIGHT, d.WIDTH, d.HEADER_HEIGHT), fill=0)

        # Line between train and weather section - full width
        bottom_divider_y = d.TRAIN_SECTION_Y + d.TRAIN_SECTION_HEIGHT
        draw.line((0, bottom_divider_y, d.WIDTH, bottom_divider_y), fill=0)

        # Vertical line for the right (hourly) lane
        draw.line((d.VERTICAL_LANE_X, d.HEADER_HEIGHT,
                   d.VERTICAL_LANE_X, d.TRAIN_SECTION_Y + d.TRAIN_SECTION_HEIGHT), fill=0)

        # Vertical line splitting the bottom section (bikes | weather)
        bottom_vertical_x = d.BOTTOM_VERTICAL_OFFSET
        draw.line((bottom_vertical_x, bottom_divider_y, bottom_vertical_x, d.HEIGHT), fill=0)
