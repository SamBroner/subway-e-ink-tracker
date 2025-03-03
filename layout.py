from PIL import Image, ImageDraw, ImageFont
from typing import Dict, List
import logging
from datetime import datetime, time, timedelta
import pytz
from dataclasses import dataclass
import os

from config import config
from fonts import fonts
from subway_service import TrainArrival
import utils
from weather_service import weather_service

logger = logging.getLogger(__name__)

# Layout configuration dataclasses
@dataclass
class WeatherSection:
    type: str  # "commute" only now
    data: dict
    width_ratio: float = 1.0

@dataclass
class WeatherLayoutConfig:
    top_sections: List[WeatherSection]
    bottom_sections: List[WeatherSection]

class LayoutManager:
    def __init__(self):
        self.display = config.display
        self.weather = config.weather
        self.subway = config.subway
        self.time = config.time
    
    def create_image(self, weather_data: dict, subway_data: List[TrainArrival]) -> Image.Image:
        """Create the display image"""
        img = self._create_base_image()
        draw = ImageDraw.Draw(img)
        
        # Draw section dividers
        self._draw_sections(draw)
        
        # Draw time
        self._draw_time(draw)
        
        # Draw subway information
        self._draw_subway_info(draw, subway_data)
        
        # Draw weather information
        self._draw_weather_info(img, draw, weather_data)

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
        
        # Line between train and weather section - stop at vertical lane
        draw.line((0, self.display.TRAIN_SECTION_Y + self.display.TRAIN_SECTION_HEIGHT,
                   self.display.MAIN_SECTION_WIDTH, self.display.TRAIN_SECTION_Y + self.display.TRAIN_SECTION_HEIGHT), fill=0)
        
        # Vertical line for the right lane
        draw.line((self.display.VERTICAL_LANE_X, self.display.HEADER_HEIGHT,
                   self.display.VERTICAL_LANE_X, self.display.HEIGHT), fill=0)
    
    def _draw_time(self, draw: ImageDraw.ImageDraw):
        """Draw the current time in the header section"""
        now = datetime.now()
        date_str = now.strftime("%a, %b %d")
        time_str = now.strftime("%I:%M:%S%p").lstrip('0').lower()
        
        font = fonts.get('header')
        
        # Calculate positions for date and time
        date_bbox = draw.textbbox((0, 0), date_str, font=font)
        time_bbox = draw.textbbox((0, 0), time_str, font=font)
        
        date_width = date_bbox[2] - date_bbox[0]
        time_width = time_bbox[2] - time_bbox[0]
        
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
    
    def _draw_weather_info(self, img: Image.Image, draw: ImageDraw.ImageDraw, weather_data: dict):
        """Draw all weather information"""
        # Draw vertical lane content
        self._draw_vertical_lane(img, draw, weather_data)
        
        # Get layout configuration
        layout = self._get_weather_layout(weather_data)
        
        # Draw commutes side by side
        if layout.top_sections:  # We'll reuse top_sections for both commutes
            self._draw_weather_section(
                img, draw,
                layout.top_sections + layout.bottom_sections,  # Combine both sections
                y=self.weather.CURRENT_Y,
                section_height=self.display.WEATHER_SECTION_HEIGHT
            )

    def _get_weather_layout(self, weather_data: dict) -> WeatherLayoutConfig:
        """Weather layout configuration"""
        # Get next four commute periods (today and tomorrow)
        commute_forecasts = weather_service.get_next_commutes(include_today=True)
        
        if len(commute_forecasts) < 2:
            logger.warning("Not enough commute forecasts")
            # Create a basic layout with just current weather
            current_weather = weather_data["current"].copy()
            current_weather['period'] = "Current Weather"
            return WeatherLayoutConfig(
                top_sections=[
                    WeatherSection("commute", current_weather, width_ratio=1.0)
                ],
                bottom_sections=[]
            )
        
        # Get the next two commute periods
        next_commutes = commute_forecasts[:2]
        
        # Update labels based on whether they're today or tomorrow
        ny_tz = pytz.timezone('America/New_York')
        today = datetime.now(ny_tz).date()
        
        for commute in next_commutes:
            commute_date = datetime.strptime(commute['date'], '%Y-%m-%d').date()
            is_tomorrow = commute_date > today
            is_morning = commute['start_time'] < '12:00'
            
            if is_tomorrow:
                commute['period'] = "Tomorrow Morning" if is_morning else "Tomorrow Evening"
            else:
                commute['period'] = "Morning Commute" if is_morning else "Evening Commute"
        
        return WeatherLayoutConfig(
            top_sections=[
                WeatherSection("commute", next_commutes[0], width_ratio=1.0)
            ],
            bottom_sections=[
                WeatherSection("commute", next_commutes[1], width_ratio=1.0)
            ]
        )

    def _draw_weather_section(self, img: Image.Image, draw: ImageDraw.ImageDraw, 
                         sections: List[WeatherSection], y: int, 
                         section_height: int):
        """Draw weather sections side by side"""
        # Calculate total width based on main section width
        total_width = self.display.MAIN_SECTION_WIDTH - 40  # Account for margins
        
        # Calculate section width (divide available space by number of sections)
        section_width = total_width // len(sections)
        
        # Track current x position - start 40px more to the left
        current_x = self.weather.MAIN_ICON_SIZE // 2 # Changed from 20 to -20
        
        for section in sections:
            self._draw_weather_section_content(
                img, draw, section,
                current_x, y,
                section_width, section_height
            )
            
            # Update x position for next section
            current_x += section_width

    def _draw_weather_section_content(self, img: Image.Image, draw: ImageDraw.ImageDraw,
                                       section: WeatherSection, x: int, y: int,
                                       width: int, height: int):
        """Draw the content for a single weather section"""
        if section.type == "commute":
            self._draw_commute_forecast(img, draw, section.data, x, y, width, height)
        else:
            logger.warning(f"Unknown section type: {section.type}")

    def _draw_commute_forecast(self, img: Image.Image, draw: ImageDraw.ImageDraw, 
                          forecast: dict, x: int, y: int, width: int, height: int):
        """Draw a single commute forecast at the specified position"""
        # Draw period label centered above weather block
        if 'period' in forecast:
            draw.text(
                (x - 40, y),
                forecast['period'],
                font=fonts.get('large'),
                fill=0,
                anchor="lt"  # Center align text
            )
        
        # Pass the center position directly to weather block
        self._draw_weather_block(
            img, draw, forecast,
            x=x,
            y=y + 35,
            icon_size=self.weather.MAIN_ICON_SIZE
        )

    def _draw_weather_block(self, img: Image.Image, draw: ImageDraw.ImageDraw, 
                    weather_data: dict, x: int, y: int,
                    icon_size: int):
        """Draw a standard weather block with icon, temp, and conditions"""
        # Get condition code safely
        condition_code = None
        if 'condition_code' in weather_data:
            condition_code = weather_data['condition_code']
        elif 'condition' in weather_data and isinstance(weather_data['condition'], dict):
            condition_code = weather_data['condition'].get('code')
        elif 'condition' in weather_data and isinstance(weather_data['condition'], str):
            condition_code = weather_data['condition']
        
        # Draw weather icon centered at x position
        icon = utils.getWeatherIcon(
            {'condition': {'code': condition_code}} if condition_code else weather_data,
            icon_size
        )
        icon_x = x - (icon_size // 2)  # Center the icon at x
        img.paste(icon, (icon_x, y), icon)
        
        # Text starts to the right of the centered icon
        text_x = x + (icon_size // 2)
        
        # Get temperature
        temp = weather_data.get('temperature', str(round(float(weather_data.get('temp_f', weather_data.get('temp', 0))))))
        temp_text = f"{temp}°"
        
        # Draw details with different font sizes
        details_text = []
        
        # Add wind speed if available
        wind_speed = weather_data.get('wind_mph', weather_data.get('wind', {}).get('mph', 0))
        if wind_speed:
            # Split into number and unit
            speed_num = str(round(float(wind_speed)))
            details_text.append((speed_num, 'mph'))
        
        # Add precipitation chance if available and >= 5%
        precipitation_chance = weather_data.get('precipitation_chance', weather_data.get('chance_of_rain', 0))
        if precipitation_chance and int(precipitation_chance) >= 15:  # Only show if 5% or higher
            # Split into number and unit
            precip_num = str(precipitation_chance)
            details_text.append((precip_num, '%'))

        # Draw temperature
        draw.text(
            (text_x, y ),
            temp_text,
            font=fonts.get('xheader'),
            fill=0
        )
        
        # Draw wind speed and precipitation chance
        if details_text:
            large_font = fonts.get('large')
            small_font = fonts.get('small')
            current_x = text_x
            
            for i, (number, unit) in enumerate(details_text):
                # Draw the number in large font
                number_width = large_font.getlength(number)
                draw.text(
                    (current_x, y + 78),
                    number,
                    font=large_font,
                    fill=0
                )
                
                # Draw the unit in small font
                unit_width = small_font.getlength(unit)
                draw.text(
                    (current_x + number_width, y + 85),
                    unit,
                    font=small_font,
                    fill=0
                )
                
                # Add separator if this isn't the last item
                if i < len(details_text) - 1:
                    separator = "|"
                    separator_width = large_font.getlength(separator)
                    draw.text(
                        (current_x + number_width + unit_width, y + 78),
                        separator,
                        font=large_font,
                        fill=0
                    )
                    current_x += number_width + unit_width + separator_width
                else:
                    current_x += number_width + unit_width
        
        # Draw conditions centered below icon
        conditions = weather_data.get('conditions', 
                                    weather_data.get('condition', {}).get('text') if isinstance(weather_data.get('condition'), dict) else weather_data.get('condition', ''))
        conditions_text = utils.shortenWeatherText(conditions)
        large_font = fonts.get('large')
        
        # Calculate text width
        conditions_bbox = draw.textbbox((0, 0), conditions_text, font=large_font)
        conditions_width = conditions_bbox[2] - conditions_bbox[0]

        # Position based on width
        if conditions_width <= 110:
            # Short text - left align at text_x
            draw.text(
                (text_x, y + 113),
                conditions_text,
                font=large_font,
                fill=0
            )
        else:
            # Longer text - centered position
            draw.text(
                (text_x - 10, y + 152),
                conditions_text,
                font=large_font,
                fill=0,
                anchor="mt"  # Center align text
            )

    def _draw_subway_info(self, draw: ImageDraw.ImageDraw, trains: List[TrainArrival]):
        """Draw subway arrival information"""
        if not trains:
            self._draw_no_trains_message(draw)
            return

        # Draw next F and G trains
        self._draw_next_trains(draw, trains)

    def _draw_next_trains(self, draw: ImageDraw.ImageDraw, trains: List[TrainArrival]):
        """Draw the next F and G train circles with upcoming trains to the right"""
        # Separate and filter trains by line
        f_trains = [t for t in trains if t.route_id == config.TRAIN_LINE_1]
        g_trains = [t for t in trains if t.route_id == config.TRAIN_LINE_2]

        def filter_trains(train_list: List[TrainArrival], max_trains: int = 6) -> List[TrainArrival]:
            forty_min_trains = [t for t in train_list if t.minutes_until_arrival <= 40]
            forty_min_trains = [t for t in forty_min_trains if t.minutes_until_arrival >= 1] # Remove 0 min trains
            filtered = forty_min_trains[:max(3, len(forty_min_trains))]
            return filtered[:min(max_trains, len(filtered))]

        next_f_trains = filter_trains(f_trains)
        next_g_trains = filter_trains(g_trains, 4)

        # Calculate dimensions
        circle_radius = 80
        logo_center_x = (self.display.MAIN_SECTION_WIDTH // 4)
        text_area_width = self.display.MAIN_SECTION_WIDTH - (logo_center_x + circle_radius + 40)  # Space after logo

        # Draw each train line section
        self._draw_train_line_section(
            draw=draw,
            trains=next_f_trains,
            route_id=config.TRAIN_LINE_1,
            logo_center_x=logo_center_x,
            logo_center_y=self.subway.F_TRAIN_Y,
            circle_radius=circle_radius,
            text_area_width=text_area_width
        )

        self._draw_train_line_section(
            draw=draw,
            trains=next_g_trains,
            route_id=config.TRAIN_LINE_2,
            logo_center_x=logo_center_x,
            logo_center_y=self.subway.G_TRAIN_Y,
            circle_radius=circle_radius,
            text_area_width=text_area_width
        )

    def _draw_train_line_section(self, draw: ImageDraw.ImageDraw, trains: List[TrainArrival],
                                route_id: str, logo_center_x: int, logo_center_y: int,
                                circle_radius: int, text_area_width: int):
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
        text_start_x = self.display.ICON_COLUMN_X + circle_radius + 100
        
        # Draw arrival times with increased line height
        line_height = 60  # Increased from 40
        
        # Adjust text_base_y based on number of trains. It's finicky, because odd and even have slightly different alignments
        if len(trains) > 5:
            # For more than 4 trains, start at the top of the section
            text_base_y = logo_center_y - 70

        elif len(trains) == 5:
            text_base_y = logo_center_y - 65
        elif len(trains) == 4:
            text_base_y = logo_center_y - 30
        elif len(trains) == 3:
            text_base_y = logo_center_y + 10
        elif len(trains) == 2:
            text_base_y = logo_center_y + 50
        elif len(trains) == 1:
            text_base_y = logo_center_y + 85
        
        for i, train in enumerate(trains):
            y = text_base_y + (i * (line_height + 12)) - line_height
            self._draw_train_arrival_time(
                draw=draw,
                train=train,
                x=text_start_x,
                y=y,
                max_width=text_area_width
            )

    def _draw_train_arrival_time(self, draw: ImageDraw.ImageDraw, train: TrainArrival,
                                x: int, y: int, max_width: int):
        """Draw a train arrival time with minutes, 'min', and arrival time"""
        time_font = fonts.get('xheader')
        small_font = fonts.get('medium')
        
        # Split arrival time into components
        arrival_hour = datetime.strptime(train.arrival_time, "%I:%M %p")
        hour_str = arrival_hour.strftime("%I:%M")
        ampm_str = arrival_hour.strftime("%p").lower()
        
        # Calculate all text widths
        min_text = "min"
        min_bbox = draw.textbbox((0, 0), min_text, font=small_font)
        min_width = min_bbox[2] - min_bbox[0]
        
        minutes_width = time_font.getlength(str(train.minutes_until_arrival))
        hour_width = time_font.getlength(hour_str)
        ampm_width = small_font.getlength(ampm_str)
        
        # Calculate total width and right-align the entire block
        total_width = minutes_width + 5 + min_width + 40 + hour_width + 5 + ampm_width
        start_x = x + max_width - total_width
        
        # Draw minutes until arrival
        draw.text(
            (start_x, y),
            str(train.minutes_until_arrival),
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

    def _draw_vertical_lane(self, img: Image.Image, draw: ImageDraw.ImageDraw, weather_data: dict):
        """Draw the vertical lane with current weather and hourly forecast"""
        # Draw current weather at the top
        self._draw_vertical_current_weather(img, draw, weather_data['current'])
        
        # Draw hourly forecast below
        hourly_data = weather_service.get_next_hours_forecast(12)
        self._draw_vertical_hourly_forecast(img, draw, hourly_data)

    def _draw_vertical_current_weather(self, img: Image.Image, draw: ImageDraw.ImageDraw, 
                                 current_weather: dict):
        """Draw current weather in the vertical lane"""
        x = self.display.VERTICAL_LANE_X + (self.display.VERTICAL_LANE_WIDTH // 2)  # Center in vertical lane
        y = self.weather.VERTICAL_CURRENT_Y
        
        # Draw "Current Weather" label centered above
        draw.text(
            (x, y),
            "Current Weather",
            font=fonts.get('large'),
            fill=0,
            anchor="mt"  # Center align text
        )
        
        self._draw_weather_block(
            img, draw, current_weather,
            x=self.display.VERTICAL_LANE_X + 80,
            y=y + 35,  # Add space for label
            icon_size=self.weather.VERTICAL_ICON_SIZE
        )

    def _draw_vertical_hourly_forecast(self, img: Image.Image, draw: ImageDraw.ImageDraw, hourly_data: List[dict]):
        """Draw hourly forecast in vertical layout"""
        x = self.display.VERTICAL_LANE_X + (self.display.VERTICAL_LANE_WIDTH // 2)
        y = self.weather.VERTICAL_HOURLY_START_Y
        icon_size = self.weather.VERTICAL_ICON_SIZE // 2
        hour_height = (self.display.HEIGHT - y) // 12  # Space for 12 hours
        
        for i, hour in enumerate(hourly_data[:12]):
            hour_y = y + (i * hour_height)
            
            # Draw time
            hour_time = datetime.fromisoformat(hour['time'].replace('Z', '+00:00')).strftime('%I%p').lstrip('0').lower()
            draw.text(
                (x - icon_size + 35, hour_y + (hour_height // 2)), 
                hour_time,
                font=fonts.get('large'),
                fill=0,
                anchor="rm"
            )
            
            # Draw icon
            icon = utils.getWeatherIcon(hour, icon_size)
            icon_x = x - (icon_size // 2)
            img.paste(icon, (icon_x, hour_y + (hour_height - icon_size) // 2), icon)
            
            # Draw temperature and precipitation chance
            temp = str(round(float(hour['temp_f'])))
            text = f"{temp}°"
            
            # Check for either 'chance_of_rain' or 'chance_of_snow' for precipitation
            precip_chance = max(
                float(hour.get('chance_of_rain', 0)),
                float(hour.get('chance_of_snow', 0))
            )

            # Only show precipitation if 5% or higher
            if precip_chance >= 15:
                text += f" {int(precip_chance)}%"
            
            draw.text(
                (x + icon_size - 35, hour_y + (hour_height // 2)),
                text,
                font=fonts.get('large'),
                fill=0,
                anchor="lm"
            )

# Create global layout manager instance
layout_manager = LayoutManager()

# Provide single image creation function
def getImage(weather_data: dict, subway_data: List[TrainArrival]) -> Image.Image:
    return layout_manager.create_image(weather_data, subway_data)