"""Bottom-left pane: classic and e-bike counts."""

from ui.fonts import fonts
import utils
from services.citibike_service import BikeAvailability
from ui.panes.base import Pane, PaneSurface, RenderContext


class CitibikePane(Pane):
    """Bottom-left: classic and e-bike counts."""

    def paint(self, surface: PaneSurface, ctx: RenderContext):
        self._draw_bike_panel(surface, ctx.bikes)

    def _draw_bike_panel(self, surface: PaneSurface, bike_data: BikeAvailability | None):
        """Draw bike counts with stacked icons on the left side of the bottom section."""
        section_y = self.weather.BOTTOM_SECTION_Y
        rows = [
            (getattr(bike_data, "classic_bikes", None), "bike", self.weather.BIKE_ICON_SIZE),
            (getattr(bike_data, "ebikes", None), "lightningbolt", self.weather.EBIKE_ICON_SIZE)
        ]

        number_font = fonts.get('xheader')
        anchor_x = self.weather.BIKE_TEXT_X
        band_height = self.display.BOTTOM_SECTION_HEIGHT - 40
        row_height = band_height / max(1, len(rows))

        for idx, (value, icon_name, icon_size) in enumerate(rows):
            row_top = section_y + idx * row_height
            center_y = row_top + row_height / 2

            icon = utils.get_ui_icon(icon_name, icon_size)
            icon_x = self.weather.BIKE_SECTION_X
            icon_y = int(center_y - (icon_size / 2))
            surface.paste(icon, (icon_x, icon_y), icon)

            number_text = "--" if value is None else str(value)
            surface.text(
                (anchor_x, center_y),
                number_text,
                font=number_font,
                fill=0,
                anchor="lm"
            )
