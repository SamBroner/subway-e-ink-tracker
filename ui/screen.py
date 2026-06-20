"""A screen: the ordered set of panes that fill the display.

`Screen.render` builds the blank frame, renders each pane into it, optionally
draws cross-pane chrome (e.g. section dividers) on top, and applies the 180°
rotation for the panel's physical orientation. Chrome is per-screen: a
full-screen image or collage with no dividers simply passes none.
"""

from dataclasses import dataclass
from typing import Callable, List, Optional

from PIL import Image, ImageDraw

from config.config import config
from data.models import DataKey
from ui.panes import Pane, RenderContext


@dataclass(frozen=True)
class ScreenProfile:
    """Display-adapter preferences for a screen.

    The current adapter still maps the runner's partial/clear flags to the
    panel modes. Keeping the profile on Screen now gives the engine a stable
    place to read waveform/binarization preferences in the next pass.
    """
    waveform: str = "DU"
    binarize: bool = False
    full_refresh_on_redraw: bool = False


RedrawPolicy = Callable[[RenderContext, Optional[RenderContext]], bool]


class Screen:
    def __init__(
        self,
        panes: List[Pane],
        chrome: Optional[Callable[[ImageDraw.ImageDraw], None]] = None,
        required_data: Optional[set[DataKey]] = None,
        redraw_policy: Optional[RedrawPolicy] = None,
        profile: Optional[ScreenProfile] = None,
    ):
        self.panes = panes
        # Optional callable(draw) for cross-pane chrome, drawn on top of the panes.
        self.chrome = chrome
        self._required_data = frozenset(required_data or set())
        self._redraw_policy = redraw_policy or (lambda _ctx, _prev_ctx: False)
        self.profile = profile or ScreenProfile()

    def requires(self) -> set[DataKey]:
        return set(self._required_data)

    def should_redraw(self, ctx: RenderContext, prev_ctx: Optional[RenderContext]) -> bool:
        return self._redraw_policy(ctx, prev_ctx)

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
