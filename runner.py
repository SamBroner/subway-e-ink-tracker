# Now import other modules
import os
import sys
from datetime import datetime
import traceback
import time
from typing import Optional, Dict, List
from dataclasses import dataclass
from subway_service import subway_service, TrainArrival
from weather_service import weather_service
from config import config
from display import Display
import logging
import logging.handlers

# Set up logging configuration
log_file = 'log.txt'
max_bytes = 5 * 1024 * 1024  # 5MB max file size

# Configure logging based on environment
if os.getenv('QUIET_MODE', 'false').lower() == 'true':
    log_level = logging.WARNING
else:
    log_level = logging.DEBUG

# Ensure log directory exists
try:
    logging.basicConfig(
        level=log_level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.handlers.RotatingFileHandler(
                log_file,
                maxBytes=max_bytes
            ),
            logging.StreamHandler() if not os.getenv('QUIET_MODE') else logging.NullHandler()
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
    last_display_update: float = 0
    last_weather_change: float = 0
    last_display_clear: float = 0

class Runner:
    def __init__(self):
        logger.info("Initializing Runner")
        self.display = Display()
        self.state = DisplayState()
        self.min_interval = 1
        self._previous_top_trains: tuple[Optional[TrainArrival], Optional[TrainArrival]] = (None, None)
    
    def handle_weather_update(self, weather_data: Dict):
        """Handle incoming weather updates"""
        self.state.weather_data = weather_data
        self.state.last_weather_change = time.time()
        self.state.last_display_clear = time.time()
        self._check_display_update(force=False)
    
    def handle_train_update(self, trains: List[TrainArrival]):
        """Handle incoming train updates"""
        now = datetime.now()
        logger.info("-" * 40)
        logger.info(f"Train update at {now.strftime('%Y-%m-%d %H:%M:%S')}")
        logger.info(f"Number of trains: {len(trains)}")
        
        for train in trains:
            logger.debug(f"Train: {train.arrival_time} ({train.minutes_until_arrival} min)")
        
        try:
            self.state.train_data = trains
            current_top_trains = self._get_top_two_trains(trains)
            if self._has_significant_change(current_top_trains):
                self._check_display_update(force=True)
            else:
                # No significant change; don't force update
                self._check_display_update()
        except Exception as e:
            logger.error(f"Error processing trains: {str(e)}")
            logger.error(traceback.format_exc())
    
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
        
        # Don't update if we don't have both weather and train data
        if not self.state.weather_data or self.state.train_data is None:
            return
            
        # Always update if this is our first update
        if self.state.last_display_update == 0:
            self._update_display()
            return
        
        # If forced (train changes), update immediately
        if force:
            self._update_display()
            return
        
        # Clear the display at least once every hour
        if (now - self.state.last_display_clear >= 3500):
            current_time = datetime.now()
            if (current_time.minute == 0):
                self._update_display(True)
            return
            
        # For weather changes, respect the minimum interval
        time_since_update = now - self.state.last_display_update

        if (time_since_update >= self.min_interval ):
            self._update_display()
            return
    
    def _update_display(self, clear: bool = False):
        """Update the display with current state"""
        try:

            self.display.update(
                weather_data=self.state.weather_data,
                train_data=self.state.train_data or [],
                partial=True,
                clear=clear
            )

            if (clear == True):
                self.state.last_display_clear = time.time()

            self.state.last_display_update = time.time()
            # Update the previous top trains after updating the display
            self._previous_top_trains = self._get_top_two_trains(self.state.train_data)
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
            
            # Start update services
            weather_service.start_updates(interval_seconds=300)  # 5 minutes
            subway_service.start_updates(interval_seconds=5)    # 5 seconds
            
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

if __name__ == "__main__":
    runner = Runner()
    runner.run()
