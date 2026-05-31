"""Bottom-right pane: enlarged current conditions, high/low, wind, precip."""

from datetime import datetime, time
from typing import Optional

from PIL import Image, ImageDraw

import clock
from ui.fonts import fonts
import utils
from services.weather_codes import RAIN_WMO_CODES, SNOW_WMO_CODES
from ui.panes.base import Pane


class WeatherOverviewPane(Pane):
    """Bottom-right: enlarged current conditions, high/low, wind, precip."""

    def render(self, img, draw, ctx):
        self._draw_weather_overview(img, draw, ctx.weather, ctx.now)

    def _draw_weather_overview(self, img: Image.Image, draw: ImageDraw.ImageDraw, weather_data: dict, now: datetime):
        """Render the enlarged current-weather card on the lower-right."""
        day_summary = None
        forecast_days = weather_data.get("forecast", {}).get("forecastday", [])
        if forecast_days:
            day_summary = forecast_days[0].get("day")
        rest_of_day_precip, rest_of_day_precip_label = self._get_rest_of_day_precip_summary(weather_data, now)
        self._draw_current_weather_large(
            img,
            draw,
            weather_data["current"],
            day_summary,
            rest_of_day_precip,
            rest_of_day_precip_label
        )

    def _get_rest_of_day_precip_summary(self, weather_data: dict, now: datetime) -> tuple[Optional[int], str]:
        """Return max precip chance and dominant precip type for the remaining hours today."""
        hourly = weather_data.get("hourly", {})
        times = hourly.get("time")
        chances = hourly.get("precipitation_probability")
        if not times or not chances:
            return None, "Precip"

        weather_codes = hourly.get("weathercode", [])
        rain_values = hourly.get("rain", [])
        snowfall_values = hourly.get("snowfall", [])

        ny_tz = clock.NY_TZ
        now = now.astimezone(ny_tz)
        rest_end = ny_tz.localize(datetime.combine(now.date(), time(23, 59)))
        rest_values = []
        rain_score = 0.0
        snow_score = 0.0

        for i, (ts, chance) in enumerate(zip(times, chances)):
            try:
                hour_dt = datetime.fromisoformat(ts)
            except ValueError:
                continue

            if hour_dt.tzinfo is None:
                hour_dt = ny_tz.localize(hour_dt)
            else:
                hour_dt = hour_dt.astimezone(ny_tz)

            if hour_dt < now:
                continue

            if hour_dt <= rest_end:
                rest_values.append(chance)
                chance_value = float(chance or 0)
                weather_code = weather_codes[i] if i < len(weather_codes) else None
                rain_amount = float(rain_values[i]) if i < len(rain_values) else 0.0
                snowfall_amount = float(snowfall_values[i]) if i < len(snowfall_values) else 0.0

                has_rain_signal = rain_amount > 0
                has_snow_signal = snowfall_amount > 0

                # If hourly amounts are zero, infer type from weather code.
                if not has_rain_signal and not has_snow_signal and weather_code is not None:
                    has_rain_signal = weather_code in RAIN_WMO_CODES
                    has_snow_signal = weather_code in SNOW_WMO_CODES

                if has_rain_signal:
                    rain_score += chance_value
                if has_snow_signal:
                    snow_score += chance_value

        if rest_values:
            max_precip = int(max(rest_values))
            if rain_score > 0 and snow_score > 0:
                if rain_score >= snow_score * 1.2:
                    return max_precip, "Rain"
                if snow_score >= rain_score * 1.2:
                    return max_precip, "Snow"
                return max_precip, "Precip"
            if rain_score > 0:
                return max_precip, "Rain"
            if snow_score > 0:
                return max_precip, "Snow"
            return max_precip, "Precip"
        return None, "Precip"

    def _get_current_precip_label(self, current_weather: dict) -> str:
        """Choose a bottom-right precip label based on dominant current precip type."""
        rain_chance = float(current_weather.get("chance_of_rain", 0) or 0)
        snow_chance = float(current_weather.get("chance_of_snow", 0) or 0)

        if rain_chance > 0 or snow_chance > 0:
            if rain_chance >= snow_chance * 1.2 and rain_chance > 0:
                return "Rain"
            if snow_chance >= rain_chance * 1.2 and snow_chance > 0:
                return "Snow"
            return "Precip"

        condition = current_weather.get("condition", {})
        condition_text = str(condition.get("text", "")).lower()
        if any(token in condition_text for token in ("snow", "sleet", "ice", "hail")):
            return "Snow"
        if any(token in condition_text for token in ("rain", "drizzle", "shower", "thunder")):
            return "Rain"
        return "Precip"

    def _draw_current_weather_large(
        self,
        img: Image.Image,
        draw: ImageDraw.ImageDraw,
        current_weather: dict,
        day_summary: Optional[dict] = None,
        rest_of_day_precip: Optional[int] = None,
        rest_of_day_precip_label: str = "Precip"
    ):
        """Render enlarged current weather card on the lower-right."""
        x = self.weather.CURRENT_SECTION_X + 10
        y = self.display.TRAIN_SECTION_Y + self.display.TRAIN_SECTION_HEIGHT + 30
        icon = utils.getWeatherIcon(current_weather, self.weather.CURRENT_ICON_SIZE)
        img.paste(icon, (x, y-15), icon)

        temp_font = fonts.get('xheader')
        detail_font = fonts.get('large')
        unit_font = fonts.get('small')
        unit_spacing = 6

        text_x = x + self.weather.CURRENT_ICON_SIZE + 40
        temp_text = f"{round(current_weather.get('temp_f', 0))}°"
        condition_text = current_weather.get('condition', {}).get('text', '')
        cond_x = x + (self.weather.CURRENT_ICON_SIZE // 2)
        draw.text((cond_x, y + self.weather.CURRENT_ICON_SIZE - 30), condition_text, font=detail_font, fill=0, anchor="mt")

        right_x = text_x + 150
        right_y = y
        high_center = low_center = None
        small_font = fonts.get('small')
        daily_rain_label_y = None
        daily_rain_value_y = None
        daily_rain_value = None
        daily_rain_label_text = "Daily Precip"
        if day_summary:
            max_temp = day_summary.get('maxtemp_f')
            min_temp = day_summary.get('mintemp_f')
            if max_temp is not None:
                draw.text((right_x, right_y - 5), "High", font=small_font, fill=0, anchor="ls")
                right_y += small_font.size + 4
                draw.text((right_x, right_y + 40), f"{round(max_temp)}°", font=temp_font, fill=0, anchor="ls")
                high_center = right_y + temp_font.size / 2
                right_y += temp_font.size + 12
            if min_temp is not None:
                draw.text((right_x, right_y - 5), "Low", font=small_font, fill=0, anchor="ls")
                right_y += small_font.size + 4
                draw.text((right_x, right_y + 40), f"{round(min_temp)}°", font=temp_font, fill=0, anchor="ls")
                low_center = right_y + temp_font.size / 2
                right_y += temp_font.size + 12
            summary_precip = day_summary.get('daily_chance_of_rain')
            if summary_precip is not None:
                daily_rain_value = summary_precip

        if rest_of_day_precip is not None:
            daily_rain_value = rest_of_day_precip
            if rest_of_day_precip_label in {"Rain", "Snow"}:
                daily_rain_label_text = f"Daily {rest_of_day_precip_label}"

        if daily_rain_value is not None:
            daily_rain_label_y = right_y - 16
            draw.text((right_x, daily_rain_label_y), daily_rain_label_text, font=small_font, fill=0, anchor="ls")
            right_y += small_font.size + 4
            daily_rain_value_y = right_y - 5
            daily_rain_value_text = f"{int(daily_rain_value)}"
            draw.text((right_x, daily_rain_value_y), daily_rain_value_text, font=fonts.get('large'), fill=0, anchor="ls")
            value_width = draw.textlength(daily_rain_value_text, font=fonts.get('large'))
            draw.text(
                (right_x + value_width + unit_spacing, daily_rain_value_y),
                "%",
                font=unit_font,
                fill=0,
                anchor="ls"
            )

        target_center = None
        if high_center and low_center:
            target_center = (high_center + low_center) / 2
        elif high_center or low_center:
            target_center = high_center or low_center
        else:
            target_center = y + self.weather.CURRENT_ICON_SIZE / 2

        temp_y = target_center - temp_font.size / 2 + 25
        draw.text((text_x - 15, temp_y), temp_text, font=temp_font, fill=0, anchor="ls")

        left_y = temp_y + temp_font.size + 12

        right_label_font = unit_font
        large_font = fonts.get('large')
        detail_x = text_x - 20

        detail_value_gap = 14  # Keeps same visual gap as previous manual layout
        detail_spacing = 8
        detail_label_offset = 45  # Label sits this many pixels above the working cursor
        unit_spacing = 6
        detail_cursor = left_y

        def draw_detail_block(label: str, value_text: str, label_y: float,
                              forced_value_y: float | None = None,
                              unit_text: str = "") -> float:
            value_y = forced_value_y if forced_value_y is not None else label_y + right_label_font.size + detail_value_gap
            draw.text((detail_x, label_y), label, font=right_label_font, fill=0, anchor="ls")
            draw.text((detail_x, value_y), value_text, font=large_font, fill=0, anchor="ls")
            cursor = value_y + large_font.size + detail_spacing
            if unit_text:
                value_width = draw.textlength(value_text, font=large_font)
                draw.text(
                    (detail_x + value_width + unit_spacing, value_y),
                    unit_text,
                    font=unit_font,
                    fill=0,
                    anchor="ls"
                )
                cursor = max(cursor, value_y + unit_font.size + detail_spacing)
            return cursor

        def block_height(unit_text: str = "") -> float:
            unit_component = unit_font.size if unit_text else 0
            return right_label_font.size + detail_value_gap + max(large_font.size, unit_component) + detail_spacing

        precip = current_weather.get('precip_chance')
        precip_label = self._get_current_precip_label(current_weather)
        has_current_precip = precip is not None and precip >= 12

        wind = current_weather.get('wind_mph')
        show_wind = wind is not None and wind >= 8
        if show_wind:
            default_wind_label_y = detail_cursor - detail_label_offset
            forced_value_y = None
            if has_current_precip and daily_rain_label_y is not None:
                max_label_y = daily_rain_label_y - block_height(" mph")
                wind_label_y = min(default_wind_label_y, max_label_y)
            elif not has_current_precip and daily_rain_label_y is not None and daily_rain_value_y is not None:
                # If we don't show rain, align wind with the daily-rain column so the gap stays filled
                wind_label_y = daily_rain_label_y
                forced_value_y = daily_rain_value_y
            else:
                wind_label_y = default_wind_label_y
            wind_label_y += 3  # slight downward nudge to match visual baseline
            detail_cursor = max(
                detail_cursor,
                draw_detail_block("Wind", f"{round(wind)}", wind_label_y, forced_value_y, unit_text="mph")
            )

        if has_current_precip:
            if daily_rain_label_y is not None and daily_rain_value_y is not None:
                detail_cursor = max(
                    detail_cursor,
                    draw_detail_block(
                        precip_label,
                        f"{int(precip)}",
                        daily_rain_label_y,
                        daily_rain_value_y,
                        unit_text="%"
                    )
                )
            else:
                rain_label_y = detail_cursor - detail_label_offset
                detail_cursor = max(
                    detail_cursor,
                    draw_detail_block(precip_label, f"{int(precip)}", rain_label_y, unit_text="%")
                )
