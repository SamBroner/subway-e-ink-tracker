from PIL import Image, ImageDraw
from typing import List, Optional
import logging
from datetime import datetime, time
import math

import clock
from config.config import config
from ui.fonts import fonts
from services.subway_service import TrainArrival
from services.citibike_service import BikeAvailability
import utils
from services.weather_service import build_next_hours_forecast
from services.weather_codes import RAIN_WMO_CODES, SNOW_WMO_CODES

logger = logging.getLogger(__name__)

class LayoutManager:
    def __init__(self):
        self.display = config.display
        self.weather = config.weather
        self.subway = config.subway
        self.time = config.time
    
    def create_image(self, weather_data: dict, subway_data: List[TrainArrival], bike_data: BikeAvailability = None, now: datetime = None) -> Image.Image:
        """Create the display image.

        ``now`` is the tz-aware reference time for all time-of-day rendering
        (header clock, train countdowns, hourly slice, rest-of-day precip).
        It defaults to ``clock.now()`` so production callers need not pass it,
        while tests can pass a fixed instant to render deterministically.
        """
        if now is None:
            now = clock.now()

        img = self._create_base_image()
        draw = ImageDraw.Draw(img)

        # Draw section dividers
        self._draw_sections(draw)

        # Draw time
        self._draw_time(draw, now)

        # Draw subway information
        self._draw_subway_info(draw, subway_data, now)

        # Draw vertical lane with hourly weather
        self._draw_vertical_lane(img, draw, weather_data, now)

        # Draw bottom content (bikes + expanded current weather)
        self._draw_bottom_sections(img, draw, weather_data, bike_data, now)

        img = img.rotate(180)

        return img
    
    def _create_base_image(self) -> Image.Image:
        """Create a blank base image"""
        return Image.new('L', (self.display.WIDTH, self.display.HEIGHT), 255)
    
    def _draw_sections(self, draw: ImageDraw.ImageDraw):
        """Draw the section dividing lines"""
        # Line between header and train section
        draw.line((0, self.display.HEADER_HEIGHT, 
                   self.display.WIDTH, self.display.HEADER_HEIGHT), fill=0)
        
        # Line between train and weather section - now full width
        bottom_divider_y = self.display.TRAIN_SECTION_Y + self.display.TRAIN_SECTION_HEIGHT
        draw.line((0, bottom_divider_y,
                   self.display.WIDTH, bottom_divider_y), fill=0)
        
        # Vertical line for the right lane
        draw.line((self.display.VERTICAL_LANE_X, self.display.HEADER_HEIGHT,
                   self.display.VERTICAL_LANE_X, self.display.TRAIN_SECTION_Y + self.display.TRAIN_SECTION_HEIGHT), fill=0)
        
        # Additional vertical line in bottom section (mirror offset)
        bottom_vertical_x = self.display.BOTTOM_VERTICAL_OFFSET
        draw.line(
            (bottom_vertical_x, bottom_divider_y, bottom_vertical_x, self.display.HEIGHT),
            fill=0
        )
    
    def _draw_time(self, draw: ImageDraw.ImageDraw, now: datetime):
        """Draw the current time in the header section"""
        date_str = now.strftime("%a, %b %d")
        time_str = now.strftime("%I:%M:%S%p").lstrip('0').lower()
        
        font = fonts.get('header')
        
        # Calculate positions for date and time
        date_bbox = draw.textbbox((0, 0), date_str, font=font)
        date_width = date_bbox[2] - date_bbox[0]

        # Position date to end 30px before midline
        date_x = (self.display.WIDTH // 2) - 30 - date_width
        # Position time to start 30px after midline
        time_x = (self.display.WIDTH // 2) + 30
        
        # Draw vertical line at midline
        line_start_y = self.time.Y - 5  # Start slightly above text
        line_end_y = self.time.Y + fonts.get('header').size + 5  # End slightly below text
        draw.line(
            (self.display.WIDTH // 2, line_start_y, 
             self.display.WIDTH // 2, line_end_y),
            fill=0,
            width=5
        )
        
        draw.text((date_x, self.time.Y), date_str, font=font, fill=0)
        draw.text((time_x, self.time.Y), time_str, font=font, fill=0)
    
    def _draw_bottom_sections(self, img: Image.Image, draw: ImageDraw.ImageDraw, weather_data: dict, bike_data: BikeAvailability | None, now: datetime):
        """Render bikes on the left and enlarged current weather on the right."""
        self._draw_bike_panel(img, draw, bike_data)
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

    def _draw_subway_info(self, draw: ImageDraw.ImageDraw, trains: List[TrainArrival], now: datetime):
        """Draw subway arrival information"""
        if not trains:
            self._draw_no_trains_message(draw)
            return

        # Draw next F and G trains
        self._draw_next_trains(draw, trains, now)

    def _get_train_display_minutes(self, train: TrainArrival, now: datetime) -> int:
        """Get countdown minutes from absolute arrival time when available."""
        if getattr(train, "arrival_timestamp", None) is not None:
            return max(0, math.floor((train.arrival_timestamp - now.timestamp()) / 60))
        return train.minutes_until_arrival

    def _draw_next_trains(self, draw: ImageDraw.ImageDraw, trains: List[TrainArrival], now: datetime):
        """Draw the next F and G train circles with upcoming trains to the right"""
        # Separate and filter trains by line
        f_trains = [t for t in trains if t.route_id == config.TRAIN_LINE_1]
        g_trains = [t for t in trains if t.route_id == config.TRAIN_LINE_2]

        def filter_trains(train_list: List[TrainArrival], max_trains: int) -> List[TrainArrival]:
            windowed = [
                t for t in train_list
                if self.subway.MIN_TRAIN_MINUTES <= self._get_train_display_minutes(t, now) <= self.subway.MAX_TRAIN_MINUTES
            ]
            windowed = windowed[:max(self.subway.MIN_TRAIN_COUNT, len(windowed))]
            windowed = sorted(windowed, key=lambda t: self._get_train_display_minutes(t, now))
            return windowed[:min(max_trains, len(windowed))]

        next_f_trains = filter_trains(f_trains, self.subway.MAX_TRAIN_COUNT)
        next_g_trains = filter_trains(g_trains, self.subway.MAX_G_TRAIN_COUNT)

        # Calculate dimensions
        circle_radius = self.subway.LOGO_RADIUS
        text_area_width = self.display.MAIN_SECTION_WIDTH - (
            self.subway.LOGO_CENTER_X + circle_radius + self.subway.TEXT_MARGIN
        )

        # Draw each train line section
        self._draw_train_line_section(
            draw=draw,
            trains=next_f_trains,
            route_id=config.TRAIN_LINE_1,
            logo_center_y=self.subway.F_TRAIN_Y,
            circle_radius=circle_radius,
            text_area_width=text_area_width,
            now=now
        )

        self._draw_train_line_section(
            draw=draw,
            trains=next_g_trains,
            route_id=config.TRAIN_LINE_2,
            logo_center_y=self.subway.G_TRAIN_Y,
            circle_radius=circle_radius,
            text_area_width=text_area_width,
            now=now
        )

    def _draw_train_line_section(self, draw: ImageDraw.ImageDraw, trains: List[TrainArrival],
                                route_id: str, logo_center_y: int,
                                circle_radius: int, text_area_width: int, now: datetime):
        """Draw a complete train line section with logo and arrival times"""
        # Draw the train line logo using the configured column position
        self._draw_train_line_logo(
            draw=draw,
            line_letter=route_id,
            x=self.display.ICON_COLUMN_X,  # Use configured position
            y=logo_center_y,
            radius=circle_radius
        )
        
        # Calculate text start position (just after the logo)
        text_start_x = self.subway.TEXT_START_X
        
        # Draw arrival times with increased line height
        line_height = self.subway.LINE_HEIGHT
        
        offset = self.subway.TEXT_BASE_OFFSETS.get(len(trains), self.subway.TEXT_BASE_DEFAULT_OFFSET)
        text_base_y = logo_center_y + offset
        
        for i, train in enumerate(trains):
            y = text_base_y + (i * (line_height + self.subway.LINE_SPACING)) - line_height
            self._draw_train_arrival_time(
                draw=draw,
                train=train,
                x=text_start_x,
                y=y,
                max_width=text_area_width,
                now=now
            )

    def _draw_train_arrival_time(self, draw: ImageDraw.ImageDraw, train: TrainArrival,
                                x: int, y: int, max_width: int, now: datetime):
        """Draw a train arrival time with minutes, 'min', and arrival time"""
        time_font = fonts.get('xheader')
        small_font = fonts.get('small')
        display_minutes = self._get_train_display_minutes(train, now)
        
        # Split arrival time into components
        arrival_hour = datetime.strptime(train.arrival_time, "%I:%M %p")
        hour_str = arrival_hour.strftime("%I:%M")
        ampm_str = arrival_hour.strftime("%p").lower()
        
        # Calculate all text widths
        min_text = "min"
        min_bbox = draw.textbbox((0, 0), min_text, font=small_font)
        min_width = min_bbox[2] - min_bbox[0]
        
        minutes_width = time_font.getlength(str(display_minutes))
        hour_width = time_font.getlength(hour_str)
        ampm_width = small_font.getlength(ampm_str)
        
        # Calculate total width and right-align the entire block
        total_width = minutes_width + 5 + min_width + 40 + hour_width + 5 + ampm_width
        start_x = x + max_width - total_width
        
        # Draw minutes until arrival
        draw.text(
            (start_x, y),
            str(display_minutes),
            font=time_font,
            fill=0,
            anchor="ls"
        )
        
        # Draw "min"
        draw.text(
            (start_x + minutes_width + 5, y),
            min_text,
            font=small_font,
            fill=0,
            anchor="ls"
        )
        
        # Draw arrival time
        time_x = start_x + minutes_width + min_width + 20
        draw.text(
            (time_x, y),
            hour_str,
            font=time_font,
            fill=0,
            anchor="ls"
        )
        
        # Draw am/pm
        draw.text(
            (time_x + hour_width, y),
            ampm_str,
            font=small_font,
            fill=0,
            anchor="ls"
        )

    def _draw_train_line_logo(self, draw: ImageDraw.ImageDraw, line_letter: str, 
                             x: int, y: int, radius: int):
        """Draw a subway train line logo"""
        draw.ellipse(
            (x - radius, y - radius, x + radius, y + radius),
            fill=0  # Black circle
        )
        draw.text(
            (x, y),
            line_letter,
            font=fonts.get('xheader'),
            fill=255,  # White text
            anchor="mm"
        )

    def _draw_no_trains_message(self, draw: ImageDraw.ImageDraw):
        """Draw message when no trains are available"""
        draw.text(
            (self.subway.PADDING_X, self.subway.NEXT_TRAIN_Y),
            "No trains",
            font=fonts.get('large'),
            fill=0
        )
        draw.text(
            (self.subway.PADDING_X, self.subway.NEXT_TRAIN_Y + 40),
            "currently",
            font=fonts.get('large'),
            fill=0
        )
        draw.text(
            (self.subway.PADDING_X, self.subway.LIST_Y),
            "No upcoming trains found",
            font=fonts.get('medium'),
            fill=0
        )

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

# Create global layout manager instance
layout_manager = LayoutManager()

# Provide single image creation function
def getImage(weather_data: dict, subway_data: List[TrainArrival], bike_data: BikeAvailability = None, now: datetime = None) -> Image.Image:
    return layout_manager.create_image(weather_data, subway_data, bike_data, now)
