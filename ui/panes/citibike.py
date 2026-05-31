"""Bottom-left pane: classic and e-bike counts."""

from PIL import Image, ImageDraw

from ui.fonts import fonts
import utils
from services.citibike_service import BikeAvailability
from ui.panes.base import Pane


class CitibikePane(Pane):
    """Bottom-left: classic and e-bike counts."""

    def render(self, img, draw, ctx):
        self._draw_bike_panel(img, draw, ctx.bikes)

    def _draw_bike_panel(self, img: Image.Image, draw: ImageDraw.ImageDraw, bike_data: BikeAvailability | None):
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
            img.paste(icon, (icon_x, icon_y), icon)

            number_text = "--" if value is None else str(value)
            draw.text(
                (anchor_x, center_y),
                number_text,
                font=number_font,
                fill=0,
                anchor="lm"
            )
