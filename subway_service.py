import logging
from datetime import datetime
from typing import List, Optional, Callable
from dataclasses import dataclass
from nyct_gtfs import NYCTFeed, Trip
from config import config
import time
import threading

logger = logging.getLogger(__name__)

@dataclass
class TrainArrival:
    minutes_until_arrival: int
    arrival_time: str
    train_id: str
    route_id: str
    
    def __eq__(self, other):
        if not isinstance(other, TrainArrival):
            return False
        return (self.minutes_until_arrival == other.minutes_until_arrival and
                self.train_id == other.train_id)

class SubwayService:
    def __init__(self):
        logger.info("Initializing SubwayService")
        self.station_id = config.STATION_ID
        logger.info(f"Using station ID from config: {config.STATION_ID}")
        logger.info(f"Station ID set to: {self.station_id}")
        self._subscribers: List[Callable[[List[TrainArrival]], None]] = []
        self._update_thread: Optional[threading.Thread] = None
        self._should_run = False
        self._current_trains: List[TrainArrival] = []
    
    def subscribe(self, callback: Callable[[List[TrainArrival]], None]):
        """Subscribe to train updates"""
        self._subscribers.append(callback)
        if self._current_trains:  # Send current data to new subscriber
            callback(self._current_trains)
    
    def start_updates(self, interval_seconds: int = 15):  # Default 15 seconds
        """Start periodic updates"""
        if self._update_thread and self._update_thread.is_alive():
            logger.warning("Update thread already running")
            return
            
        self._should_run = True
        self._update_thread = threading.Thread(target=self._update_loop, args=(interval_seconds,))
        self._update_thread.daemon = True
        self._update_thread.start()
        logger.info(f"Started subway update thread with {interval_seconds}s interval")
    
    def stop_updates(self):
        """Stop periodic updates"""
        self._should_run = False
        if self._update_thread:
            self._update_thread.join()
            self._update_thread = None
        logger.info("Stopped subway updates")
    
    def _should_notify(self, new_trains: List[TrainArrival]) -> bool:
        """Determine if we should notify subscribers based on changes"""
        if not self._current_trains or not new_trains:
            return True
            
        # Always notify if first or second train changed
        for i in range(min(2, len(new_trains))):
            if i >= len(self._current_trains):
                return True
            if new_trains[i] != self._current_trains[i]:
                return True
        
        return False
    
    def _update_loop(self, interval_seconds: int):
        """Background update loop"""
        while self._should_run:
            try:
                new_trains = self.get_upcoming_trains()
                if self._should_notify(new_trains):
                    self._current_trains = new_trains
                    self._notify_subscribers(new_trains)
                time.sleep(interval_seconds)
            except Exception as e:
                logger.error(f"Error in update loop: {str(e)}")
                time.sleep(interval_seconds)
    
    def _notify_subscribers(self, trains: List[TrainArrival]):
        """Notify all subscribers of new train data"""
        for subscriber in self._subscribers:
            try:
                subscriber(trains)
            except Exception as e:
                logger.error(f"Error notifying subscriber: {str(e)}")
    
    def get_upcoming_trains(self) -> List[TrainArrival]:
        """Get list of upcoming trains for the configured station"""
        try:
            logger.debug(f"Fetching train data for station {self.station_id}")
            
            # Fetch trains for the first line
            logger.debug(f"Creating feed for line {config.TRAIN_LINE_1}")
            feed_f = NYCTFeed(config.TRAIN_LINE_1)
            logger.debug(f"Raw feed data for {config.TRAIN_LINE_1}: {feed_f}")
            # Debug: Print all unique station IDs in the feed
            station_ids = set()
            for trip in feed_f.trips:
                for stop in trip.stop_time_updates:
                    station_ids.add(stop.stop_id)
            logger.debug(f"Available station IDs in {config.TRAIN_LINE_1} feed: {sorted(list(station_ids))}")
            
            trains_f = feed_f.filter_trips(headed_for_stop_id=self.station_id)
            logger.info(f"Found {len(trains_f)} trains for line {config.TRAIN_LINE_1}")
            if not trains_f:
                logger.debug("No trains found for line F, checking feed status...")
                logger.debug(f"Feed timestamp: {feed_f.timestamp if hasattr(feed_f, 'timestamp') else 'No timestamp'}")
                logger.debug(f"Total trips in feed: {len(feed_f.trips) if hasattr(feed_f, 'trips') else 'No trips attribute'}")
            
            # Fetch trains for the second line
            logger.debug(f"Creating feed for line {config.TRAIN_LINE_2}")
            feed_g = NYCTFeed(config.TRAIN_LINE_2)
            logger.debug(f"Raw feed data for {config.TRAIN_LINE_2}: {feed_g}")
            
            # Debug: Print all unique station IDs in the feed
            station_ids = set()
            for trip in feed_g.trips:
                for stop in trip.stop_time_updates:
                    station_ids.add(stop.stop_id)
            logger.debug(f"Available station IDs in {config.TRAIN_LINE_2} feed: {sorted(list(station_ids))}")
            
            trains_g = feed_g.filter_trips(headed_for_stop_id=self.station_id)
            logger.info(f"Found {len(trains_g)} trains for line {config.TRAIN_LINE_2}")
            if not trains_g:
                logger.debug("No trains found for line G, checking feed status...")
                logger.debug(f"Feed timestamp: {feed_g.timestamp if hasattr(feed_g, 'timestamp') else 'No timestamp'}")
                logger.debug(f"Total trips in feed: {len(feed_g.trips) if hasattr(feed_g, 'trips') else 'No trips attribute'}")
            
            # Combine trains from both lines
            trains = trains_f + trains_g
            
            if not trains:
                logger.warning("No trains found in feed")
                return []
            
            arrivals = []
            for train in trains:
                logger.debug(f"Processing train: {train.trip_id if hasattr(train, 'trip_id') else 'No trip_id'}")
                arrival = self._process_train(train)
                if arrival:
                    logger.debug(f"Processed train arrival: {arrival.arrival_time} ({arrival.minutes_until_arrival} min)")
                    arrivals.append(arrival)
                else:
                    logger.warning(f"Could not process train: {train}")
            
            sorted_arrivals = sorted(arrivals, key=lambda x: x.minutes_until_arrival)
            logger.info(f"Returning {len(sorted_arrivals)} processed train arrivals")
            return sorted_arrivals
            
        except Exception as e:
            logger.error(f"Error getting subway data: {str(e)}", exc_info=True)
            return []
    
    def _process_train(self, train: Trip) -> Optional[TrainArrival]:
        """Process a single train and return its arrival information"""
        try:
            logger.debug(f"Processing train with ID: {train.trip_id if hasattr(train, 'trip_id') else 'No trip_id'}")
            logger.debug(f"Train stop updates: {train.stop_time_updates if hasattr(train, 'stop_time_updates') else 'No updates'}")
            
            target_stop = next((stop for stop in train.stop_time_updates 
                              if stop.stop_id == self.station_id), None)
            
            if not target_stop:
                logger.debug(f"No target stop found for station {self.station_id}")
                return None
                
            if not target_stop.arrival:
                logger.debug("Target stop has no arrival time")
                return None
            
            arrival_time = target_stop.arrival
            now = datetime.now()
            minutes = max(0, round((arrival_time - now).total_seconds() / 60))
            
            logger.debug(f"Calculated arrival: {minutes} minutes from now at {arrival_time}")
            
            return TrainArrival(
                minutes_until_arrival=minutes,
                arrival_time=arrival_time.strftime("%I:%M %p"),
                train_id=train.trip_id,
                route_id=train.route_id
            )
            
        except Exception as e:
            logger.error(f"Error processing train: {str(e)}", exc_info=True)
            return None

# Create a global subway service instance
subway_service = SubwayService()