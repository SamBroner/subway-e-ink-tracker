"""A minimal full-bleed pane: a centered greeting, for experimentation."""

from ui.fonts import fonts
from ui.panes.base import Pane, PaneSurface, RenderContext


class HelloPane(Pane):
    """Draws a centered greeting; ignores the render context."""

    def paint(self, surface: PaneSurface, ctx: RenderContext):
        cx = self.x + self.w // 2
        cy = self.y + self.h // 2
        surface.text((cx, cy), "Hello, World!", font=fonts.get('header'), fill=0, anchor="mm")
