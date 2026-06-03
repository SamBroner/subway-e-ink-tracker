"""Header pane: date and current time."""

from datetime import datetime

from ui.fonts import fonts
from ui.panes.base import Pane, PaneSurface, RenderContext


class DatePane(Pane):
    """Header: date and current time."""

    def paint(self, surface: PaneSurface, ctx: RenderContext):
        self._draw_time(surface, ctx.now)

    def _draw_time(self, surface: PaneSurface, now: datetime):
        """Draw the current time in the header section"""
        date_str = now.strftime("%a, %b %d")
        time_str = now.strftime("%I:%M:%S%p").lstrip('0').lower()

        font = fonts.get('header')

        # Calculate positions for date and time
        date_bbox = surface.textbbox((0, 0), date_str, font=font)
        date_width = date_bbox[2] - date_bbox[0]

        # Position date to end 30px before midline
        date_x = (self.display.WIDTH // 2) - 30 - date_width
        # Position time to start 30px after midline
        time_x = (self.display.WIDTH // 2) + 30

        # Draw vertical line at midline
        line_start_y = self.time.Y - 5  # Start slightly above text
        line_end_y = self.time.Y + fonts.get('header').size + 5  # End slightly below text
        surface.line(
            (self.display.WIDTH // 2, line_start_y,
             self.display.WIDTH // 2, line_end_y),
            fill=0,
            width=5
        )

        surface.text((date_x, self.time.Y), date_str, font=font, fill=0)
        surface.text((time_x, self.time.Y), time_str, font=font, fill=0)
