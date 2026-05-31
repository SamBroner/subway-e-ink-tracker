# Now import other modules
import os
from datetime import datetime
import traceback
import time
from typing import Optional, Dict, List
from dataclasses import dataclass
from services.subway_service import subway_service, TrainArrival, SubwayResult
from services.weather_service import weather_service
from services.citibike_service import citibike_service, BikeAvailability
from config.config import config
from ui.display import Display
import logging
import logging.handlers

# Set up logging configuration
log_file = 'log.txt'
max_bytes = 5 * 1024 * 1024  # 5MB max file size

# Configure logging based on environment
quiet_mode = os.getenv('QUIET_MODE', 'false').lower() == 'true'
log_level = logging.WARNING if quiet_mode else logging.DEBUG

# Ensure log directory exists
try:
    logging.basicConfig(
        level=log_level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.handlers.RotatingFileHandler(
                log_file,
                maxBytes=max_bytes,
                backupCount=5
            ),
            logging.StreamHandler() if not quiet_mode else logging.NullHandler()
        ],
        force=True
    )
except Exception as e:
    print(f"Error setting up logging: {str(e)}")
    raise

logger = logging.getLogger(__name__)

@dataclass
class DisplayState:
    weather_data: Optional[Dict] = None
    train_data: Optional[List[TrainArrival]] = None
    subway_unavailable: bool = False
    bike_data: Optional[BikeAvailability] = None
    last_display_update: float = 0
    last_display_clear: float = 0

class Runner:
    def __init__(self):
        logger.info("Initializing Runner")
        self.display = Display()
        self.state = DisplayState()
        self.min_interval = config.timing.DISPLAY_MIN_INTERVAL_SECONDS
        self._previous_top_trains: tuple[Optional[TrainArrival], Optional[TrainArrival]] = (None, None)
        self._previous_subway_unavailable: bool = False

    def handle_weather_update(self, weather_data: Dict):
        """Handle incoming weather updates"""
        self.state.weather_data = weather_data
        self._check_display_update(force=False)
    
    def handle_train_update(self, result: SubwayResult):
        """Handle incoming train updates"""
        now = datetime.now()
        trains = result.trains
        logger.info("-" * 40)
        logger.info(f"Train update at {now.strftime('%Y-%m-%d %H:%M:%S')}")
        logger.info(f"Number of trains: {len(trains)} (service_unavailable={result.service_unavailable})")

        for train in trains:
            logger.debug(f"Train: {train.arrival_time} ({train.minutes_until_arrival} min)")

        try:
            self.state.train_data = trains
            self.state.subway_unavailable = result.service_unavailable
            current_top_trains = self._get_top_two_trains(trains)
            availability_changed = result.service_unavailable != self._previous_subway_unavailable
            if availability_changed or self._has_significant_change(current_top_trains):
                self._check_display_update(force=True)
            else:
                # No significant change; don't force update
                self._check_display_update()
        except Exception as e:
            logger.error(f"Error processing trains: {str(e)}")
            logger.error(traceback.format_exc())
    
    def handle_bike_update(self, availability: BikeAvailability):
        """Handle incoming bike availability updates"""
        logger.info(f"Bike update: {availability.classic_bikes} classic, {availability.ebikes} ebikes")
        self.state.bike_data = availability
        self._check_display_update(force=False)
    
    def _get_top_two_trains(self, trains: List[TrainArrival]) -> tuple[Optional[TrainArrival], Optional[TrainArrival]]:
        """Get the first two trains from the list"""
        return (
            trains[0] if len(trains) > 0 else None,
            trains[1] if len(trains) > 1 else None
        )
    
    def _has_significant_change(self, current_trains: tuple[Optional[TrainArrival], Optional[TrainArrival]]) -> bool:
        """Check if there's been a significant change in train times"""
        if not self._previous_top_trains[0] and current_trains[0]:
            return True  # First train appeared
        if not current_trains[0]:
            return True  # No trains (should show no trains message)
            
        # Check if either of the top two trains have changed
        for prev, curr in zip(self._previous_top_trains, current_trains):
            if prev and curr:
                if (prev.train_id != curr.train_id or 
                    prev.minutes_until_arrival != curr.minutes_until_arrival):
                    return True
            elif prev != curr:  # One is None and the other isn't
                return True
        
        return False
    
    def _check_display_update(self, force: bool = False):
        """Check if we should update the display"""
        now = time.time()

        # Don't update if we don't have essential data (bike data is optional)
        if not self.state.weather_data or self.state.train_data is None:
            logger.debug(f"[DISPLAY SKIP] Missing essential data - weather: {self.state.weather_data is not None}, trains: {self.state.train_data is not None}")
            return

        # Warn if bike data hasn't arrived yet (but don't block display)
        if self.state.bike_data is None:
            logger.warning("[DISPLAY] Bike data not available, displaying without it")
            
        # Always update if this is our first update
        if self.state.last_display_update == 0:
            logger.info("[DISPLAY UPDATE] First update")
            self._update_display()
            return

        # If forced (train changes), update immediately
        if force:
            logger.info("[DISPLAY UPDATE] Forced update (train change)")
            self._update_display()
            return

        # Clear the display at the top of every hour (aligned to clock time)
        current_time = datetime.now()
        if (current_time.minute == 0) and (now - self.state.last_display_clear >= 3500):
            logger.info("[DISPLAY UPDATE] Hourly clear")
            self._update_display(True)
            return

        # For weather changes, respect the minimum interval
        time_since_update = now - self.state.last_display_update

        if (time_since_update >= self.min_interval ):
            logger.info(f"[DISPLAY UPDATE] Interval passed ({time_since_update:.1f}s >= {self.min_interval}s)")
            self._update_display()
            return
        else:
            logger.debug(f"[DISPLAY SKIP] Min interval not met ({time_since_update:.1f}s < {self.min_interval}s)")
    
    def _update_display(self, clear: bool = False):
        """Update the display with current state"""
        try:

            partial = not clear

            self.display.update(
                weather_data=self.state.weather_data,
                train_data=self.state.train_data or [],
                bike_data=self.state.bike_data,
                subway_unavailable=self.state.subway_unavailable,
                partial=partial,
                clear=clear
            )

            if (clear == True):
                self.state.last_display_clear = time.time()

            self.state.last_display_update = time.time()
            # Update the previous top trains after updating the display
            self._previous_top_trains = self._get_top_two_trains(self.state.train_data)
            self._previous_subway_unavailable = self.state.subway_unavailable
        except Exception as e:
            logger.error(f"Error updating display: {str(e)}")
    
    def run(self):
        """Main run method"""
        try:
            logger.info("Starting services...")
            
            # Initialize display
            self.display.initialize()
            
            # Subscribe to services
            weather_service.subscribe(self.handle_weather_update)
            subway_service.subscribe(self.handle_train_update)
            citibike_service.subscribe(self.handle_bike_update)
            
            # Start update services
            weather_service.start_updates(interval_seconds=config.timing.WEATHER_UPDATE_SECONDS)
            subway_service.start_updates(interval_seconds=config.timing.SUBWAY_UPDATE_SECONDS)
            citibike_service.start_updates(interval_seconds=config.timing.CITIBIKE_UPDATE_SECONDS)
            
            # Keep the main thread running
            try:
                while True:
                    time.sleep(1)
                    self._check_display_update()
            except KeyboardInterrupt:
                logger.info("Shutting down...")
                
        except Exception as e:
            logger.error(f"Error in main runner: {str(e)}")
        finally:
            # Clean shutdown
            subway_service.stop_updates()
            weather_service.stop_updates()
            citibike_service.stop_updates()

if __name__ == "__main__":
    runner = Runner()
    runner.run()
