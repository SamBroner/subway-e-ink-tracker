import os
from dotenv import load_dotenv
from dataclasses import dataclass
import logging

logger = logging.getLogger(__name__)

# Force reload environment variables. Load the .env that sits next to this file
# (config/.env) explicitly, so it resolves regardless of the current working
# directory — the package layout keeps config.py and .env in the config/ package.
load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env'), override=True)

@dataclass
class DisplayConfig:
    WIDTH: int = 825
    HEIGHT: int = 1200
    
    def __post_init__(self):
        self.HEADER_HEIGHT = self.HEIGHT // 9 # 1/8th of the height
        self.TRAIN_SECTION_HEIGHT =  (self.HEIGHT * 2) // 3 # ((self.HEIGHT - self.HEADER_HEIGHT) * 2) // 4  # Half the height 
        self.WEATHER_SECTION_HEIGHT = self.HEIGHT - self.HEADER_HEIGHT - self.TRAIN_SECTION_HEIGHT # The rest
        
        # Add vertical lane dimensions
        self.VERTICAL_LANE_WIDTH = self.WIDTH // 3
        self.MAIN_SECTION_WIDTH = self.WIDTH - self.VERTICAL_LANE_WIDTH
        
        # Central column position for train and weather icons
        self.ICON_COLUMN_X = 100 # self.MAIN_SECTION_WIDTH // 6
        
        self.HEADER_Y = 0
        self.TRAIN_SECTION_Y = self.HEADER_HEIGHT
        self.WEATHER_SECTION_Y = self.TRAIN_SECTION_Y + self.TRAIN_SECTION_HEIGHT
        
        # Add vertical lane position
        self.VERTICAL_LANE_X = self.MAIN_SECTION_WIDTH
        self.BOTTOM_SECTION_HEIGHT = self.HEIGHT - self.WEATHER_SECTION_Y
        self.BOTTOM_VERTICAL_OFFSET = self.MAIN_SECTION_WIDTH // 2

@dataclass
class WeatherConfig:
    def __init__(self, display: DisplayConfig):
        # Adjust main icon sizes for new layout
        self.MAIN_ICON_SIZE = 165
        self.SMALL_ICON_SIZE = 80 # round(display.WEATHER_SECTION_HEIGHT / 4)
        self.VERTICAL_ICON_SIZE = 165  # New size for vertical lane

        self.CURRENT_X = 20
        self.CURRENT_Y = display.WEATHER_SECTION_Y + 20
        
        # Add vertical lane positions
        self.VERTICAL_CURRENT_Y = display.TRAIN_SECTION_Y + 20
        self.VERTICAL_HOURLY_START_Y = self.VERTICAL_CURRENT_Y + self.VERTICAL_ICON_SIZE + 40
        
        self.FORECAST_Y = self.CURRENT_Y + self.MAIN_ICON_SIZE + 40
        spacing = (display.WIDTH - 60) // 3
        self.TODAY_X = 20
        self.TOMORROW_X = self.TODAY_X + spacing
        self.OVERMORROW_X = self.TOMORROW_X + spacing

        # Bottom section (bikes + enlarged current weather)
        self.BOTTOM_SECTION_Y = display.WEATHER_SECTION_Y + 20
        self.BIKE_SECTION_X = 20
        self.BIKE_SECTION_WIDTH = display.BOTTOM_VERTICAL_OFFSET - self.BIKE_SECTION_X - 20
        self.BIKE_ICON_SIZE = 100
        self.EBIKE_ICON_SIZE = 80
        self.BIKE_TEXT_X = self.BIKE_SECTION_X + self.BIKE_ICON_SIZE + 45
        self.BIKE_ROW_COUNT = 2
        self.CURRENT_SECTION_X = display.BOTTOM_VERTICAL_OFFSET
        self.CURRENT_SECTION_WIDTH = display.WIDTH - self.CURRENT_SECTION_X - 20
        self.CURRENT_SECTION_TOP = self.BOTTOM_SECTION_Y
        self.CURRENT_ICON_SIZE = 220

@dataclass
class SubwayConfig:
    def __init__(self, display: DisplayConfig):
        self.SECTION_Y = display.TRAIN_SECTION_Y
        self.SECTION_HEIGHT = display.TRAIN_SECTION_HEIGHT
        self.NEXT_TRAIN_Y = self.SECTION_Y + 20
        self.LIST_Y = self.NEXT_TRAIN_Y + 100
        self.PADDING_X = 20
        
        # Position F and G trains at 1/4 and 3/4 of the section height
        self.F_TRAIN_Y = self.SECTION_Y + (self.SECTION_HEIGHT // 2) - (self.SECTION_HEIGHT // 4)
        self.G_TRAIN_Y = self.SECTION_Y + (self.SECTION_HEIGHT // 2) + (self.SECTION_HEIGHT // 4)
        
        # Train logo and text layout
        self.LOGO_RADIUS = 80
        self.LOGO_CENTER_X = display.MAIN_SECTION_WIDTH // 4
        self.TEXT_MARGIN = 40
        self.TEXT_PADDING = 100
        self.TEXT_START_X = display.ICON_COLUMN_X + self.LOGO_RADIUS + self.TEXT_PADDING
        self.LINE_HEIGHT = 60
        self.LINE_SPACING = 12
        self.TEXT_BASE_OFFSETS = {
            1: 85,
            2: 50,
            3: 10,
            4: -30,
            5: -65
        }
        self.TEXT_BASE_DEFAULT_OFFSET = -70
        
        # Train filtering limits
        self.MIN_TRAIN_MINUTES = 1
        self.MAX_TRAIN_MINUTES = 40
        self.MIN_TRAIN_COUNT = 3
        self.MAX_TRAIN_COUNT = 6
        self.MAX_G_TRAIN_COUNT = 4

@dataclass
class TimingConfig:
    WEATHER_UPDATE_SECONDS: int = 300
    SUBWAY_UPDATE_SECONDS: int = 5
    CITIBIKE_UPDATE_SECONDS: int = 60
    DISPLAY_MIN_INTERVAL_SECONDS: int = 1
    DISPLAY_CLEAR_COOLDOWN_SECONDS: int = 5

@dataclass
class TimeConfig:
    def __init__(self, display: DisplayConfig, FONT_SIZES):
        self.Y = display.HEADER_Y + (display.HEADER_HEIGHT // 2) - FONT_SIZES['header'] // 2 - 8
        self.X = display.WIDTH // 2

class Config:
    def __init__(self):
        # Environment variables
        logger.info("Loading configuration from environment variables...")
        self.DEBUG = os.getenv('DEBUG', 'false').lower() == 'true'
        self.STATION_ID = os.getenv('STATION_ID')
        self.TRAIN_LINE_1 = os.getenv('TRAIN_LINE_1')
        self.TRAIN_LINE_2 = os.getenv('TRAIN_LINE_2')
        self.CITIBIKE_STATION_ID = os.getenv('CITIBIKE_STATION_ID')
        self.CITIBIKE_STATION_NAME = os.getenv('CITIBIKE_STATION_NAME')

        if not self.STATION_ID:
            raise ValueError("STATION_ID must be set in .env file")
        if not self.TRAIN_LINE_1:
            raise ValueError("TRAIN_LINE_1 must be set in .env file")
        if not self.TRAIN_LINE_2:
            raise ValueError("TRAIN_LINE_2 must be set in .env file")
        if not self.CITIBIKE_STATION_ID:
            raise ValueError("CITIBIKE_STATION_ID must be set in .env file")
        if not self.CITIBIKE_STATION_NAME:
            raise ValueError("CITIBIKE_STATION_NAME must be set in .env file")
        
        # Display configurations
        self.display = DisplayConfig()
        self.weather = WeatherConfig(self.display)
        self.subway = SubwayConfig(self.display)
        self.timing = TimingConfig()
        
        # Font sizes
        self.FONT_SIZES = {
            'small': 18,
            'medium': 24,
            'large': 30,
            'xlarge': 36,
            'xxlarge': 42,
            'header': 60,
            'xheader': 72,
        }

        self.time = TimeConfig(self.display, self.FONT_SIZES)
        
        # Commute time configurations
        self.commute_times = {
            'morning': {
                'start': '07:00',
                'end': '10:00',
                'label': 'Morning Commute'
            },
            'evening': {
                'start': '17:00', 
                'end': '19:00',
                'label': 'Evening Commute'
            }
        }

        # Weather coordinates (defaulting to NYC coordinates if not specified)
        self.WEATHER_COORDS = (
            float(os.getenv('WEATHER_LAT', '40.7128')), 
            float(os.getenv('WEATHER_LON', '-74.0060'))
        )

# Create a global configuration instance
config = Config()
