import logging
from typing import Optional, Callable
from dataclasses import dataclass
import requests
from config.config import config
import time
import threading

logger = logging.getLogger(__name__)

@dataclass
class BikeAvailability:
    classic_bikes: int
    ebikes: int
    station_id: str
    station_name: str

class CitibikeService:
    def __init__(self):
        logger.info("Initializing CitibikeService")
        self.station_id = config.CITIBIKE_STATION_ID
        logger.info(f"Using station ID from config: {config.CITIBIKE_STATION_ID}")
        self._subscribers: list[Callable[[BikeAvailability], None]] = []
        self._update_thread: Optional[threading.Thread] = None
        self._should_run = False
        self._current_availability: Optional[BikeAvailability] = None
    
    def subscribe(self, callback: Callable[[BikeAvailability], None]):
        """Subscribe to bike availability updates"""
        self._subscribers.append(callback)
        if self._current_availability:  # Send current data to new subscriber
            callback(self._current_availability)
    
    def start_updates(self, interval_seconds: int = 60):  # Default 60 seconds
        """Start periodic updates"""
        if self._update_thread and self._update_thread.is_alive():
            logger.warning("Update thread already running")
            return
            
        self._should_run = True
        self._update_thread = threading.Thread(target=self._update_loop, args=(interval_seconds,))
        self._update_thread.daemon = True
        self._update_thread.start()
        logger.info(f"Started citibike update thread with {interval_seconds}s interval")
    
    def stop_updates(self):
        """Stop periodic updates"""
        self._should_run = False
        if self._update_thread:
            self._update_thread.join()
            self._update_thread = None
        logger.info("Stopped citibike updates")
    
    def _should_notify(self, new_availability: BikeAvailability) -> bool:
        """Determine if we should notify subscribers based on changes"""
        if not self._current_availability:
            return True
        
        return (new_availability.classic_bikes != self._current_availability.classic_bikes or
                new_availability.ebikes != self._current_availability.ebikes)
    
    def _update_loop(self, interval_seconds: int):
        """Background update loop"""
        while self._should_run:
            try:
                availability = self.get_bike_availability()
                if availability and self._should_notify(availability):
                    self._current_availability = availability
                    self._notify_subscribers(availability)
                time.sleep(interval_seconds)
            except Exception as e:
                logger.error(f"Error in update loop: {str(e)}")
                time.sleep(interval_seconds)
    
    def _notify_subscribers(self, availability: BikeAvailability):
        """Notify all subscribers of new bike data"""
        for subscriber in self._subscribers:
            try:
                subscriber(availability)
            except Exception as e:
                logger.error(f"Error notifying subscriber: {str(e)}")
    
    def get_bike_availability(self) -> Optional[BikeAvailability]:
        """Get bike availability for the configured station"""
        try:
            logger.debug(f"Fetching bike data for station {self.station_id}")
            
            # GBFS API endpoint
            url = "https://gbfs.lyft.com/gbfs/2.3/bkn/en/station_status.json"
            
            headers = {"User-Agent": "simple-e-ink-citibike/1.0"}
            response = requests.get(url, headers=headers, timeout=10)
            response.raise_for_status()
            
            data = response.json()
            
            # Find our station in the data
            station_data = None
            for station in data.get("data", {}).get("stations", []):
                if station.get("station_id") == self.station_id:
                    station_data = station
                    break
            
            if not station_data:
                logger.warning(f"Station {self.station_id} not found in feed")
                return None
            
            # Parse vehicle types to get accurate counts
            classic_bikes = 0
            ebikes = 0
            
            if "vehicle_types_available" in station_data:
                for vehicle_type in station_data["vehicle_types_available"]:
                    vehicle_type_id = vehicle_type.get("vehicle_type_id")
                    count = vehicle_type.get("count", 0)
                    if vehicle_type_id == "1":  # Classic bikes
                        classic_bikes = count
                    elif vehicle_type_id == "2":  # E-bikes
                        ebikes = count
            
            # Get station name from config or use a default
            station_name = getattr(config, 'CITIBIKE_STATION_NAME', 'Citi Bike Station')
            
            availability = BikeAvailability(
                classic_bikes=classic_bikes,
                ebikes=ebikes,
                station_id=self.station_id,
                station_name=station_name
            )
            
            logger.info(f"Found {classic_bikes} classic bikes and {ebikes} ebikes at station {self.station_id}")
            return availability
            
        except Exception as e:
            logger.error(f"Error getting citibike data: {str(e)}", exc_info=True)
            return None

# Create a global citibike service instance
citibike_service = CitibikeService()

