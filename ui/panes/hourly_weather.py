"""Right-lane pane: the next 12 hours of forecast."""

from datetime import datetime
from typing import List

from PIL import Image, ImageDraw

from ui.fonts import fonts
import utils
from services.weather_service import build_next_hours_forecast
from ui.panes.base import Pane


class HourlyWeatherPane(Pane):
    """Right lane: the next 12 hours of forecast."""

    def paint(self, surface, ctx):
        # Pass the PaneSurface as both the image (icon paste) and draw target;
        # it duck-types Image.paste and the ImageDraw calls the helpers use.
        self._draw_vertical_lane(surface, surface, ctx.weather, ctx.now)

    def _draw_vertical_lane(self, img: Image.Image, draw: ImageDraw.ImageDraw, weather_data: dict, now: datetime):
        """Draw the vertical lane with hourly forecast only."""
        hourly_data = build_next_hours_forecast(weather_data, now, 12)
        self._draw_vertical_hourly_forecast(img, draw, hourly_data)

    def _draw_vertical_hourly_forecast(self, img: Image.Image, draw: ImageDraw.ImageDraw, hourly_data: List[dict]):
        """Draw hourly forecast in vertical layout"""
        x = self.display.VERTICAL_LANE_X + (self.display.VERTICAL_LANE_WIDTH // 2) + 15
        y = self.weather.VERTICAL_CURRENT_Y - 15
        icon_size = self.weather.VERTICAL_ICON_SIZE // 2
        available_height = max(1, self.weather.BOTTOM_SECTION_Y - y - 30)
        hour_height = available_height / max(1, len(hourly_data))

        for i, hour in enumerate(hourly_data[:12]):
            hour_y = int(y + i * hour_height)
            chance_of_precipitation = hour.get('chance_of_precipitation')
            if chance_of_precipitation is None:
                precip_chance = max(
                    float(hour.get('chance_of_rain', 0)),
                    float(hour.get('chance_of_snow', 0))
                )
            else:
                precip_chance = float(chance_of_precipitation)
            center_x = x

            # Draw time
            hour_time = datetime.fromisoformat(hour['time'].replace('Z', '+00:00')).strftime('%I%p').lstrip('0').lower()
            draw.text(
                (center_x - icon_size + 35, hour_y + int(hour_height // 2)),
                hour_time,
                font=fonts.get('large'),
                fill=0,
                anchor="rm"
            )

            # Draw icon
            icon = utils.getWeatherIcon(hour, icon_size)
            icon_x = center_x - (icon_size // 2)
            img.paste(icon, (icon_x, hour_y + int((hour_height - icon_size) // 2)), icon)

            # Draw temperature and precipitation chance
            temp = str(round(float(hour['temp_f'])))
            temp_pos = (center_x + icon_size - 35, hour_y + int(hour_height // 2))
            draw.text(temp_pos, f"{temp}°", font=fonts.get('large'), fill=0, anchor="lm")

            if precip_chance >= 15:
                draw.text(
                    (temp_pos[0], temp_pos[1] + 26),
                    f"{int(precip_chance)}%",
                    font=fonts.get('medium'),
                    fill=0,
                    anchor="lm"
                )
