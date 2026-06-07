import logging
from datetime import datetime
from typing import List, Optional, Callable
from dataclasses import dataclass
from nyct_gtfs import NYCTFeed, Trip
from config.config import config
import threading
import requests

logger = logging.getLogger(__name__)

@dataclass
class TrainArrival:
    minutes_until_arrival: int
    arrival_time: str
    arrival_timestamp: float
    train_id: str
    route_id: str

    def __eq__(self, other):
        if not isinstance(other, TrainArrival):
            return False
        return (self.minutes_until_arrival == other.minutes_until_arrival and
                self.train_id == other.train_id)


@dataclass
class SubwayResult:
    """A subway snapshot: the upcoming trains plus which line feeds we failed
    to reach. Distinguishes "feeds are up, no trains" from "feeds unreachable".
    """
    trains: List[TrainArrival]
    unavailable_lines: frozenset = frozenset()

    @property
    def service_unavailable(self) -> bool:
        """True only when none of the configured line feeds could be reached.

        A single failing feed is not "service down" — the working feed still
        gives us a real (possibly empty) picture, so that renders as normal.
        """
        configured = {config.TRAIN_LINE_1, config.TRAIN_LINE_2}
        return configured.issubset(self.unavailable_lines)

class SubwayService:
    def __init__(self):
        logger.info("Initializing SubwayService")
        self.station_id = config.STATION_ID
        self.request_timeout_seconds = 10
        logger.info(f"Using station ID from config: {config.STATION_ID}")
        logger.info(f"Station ID set to: {self.station_id}")
        self._subscribers: List[Callable[[SubwayResult], None]] = []
        self._update_thread: Optional[threading.Thread] = None
        self._should_run = False
        self._stop_event = threading.Event()
        self._current_result: Optional[SubwayResult] = None

    def _fetch_feed(self, line_id: str) -> NYCTFeed:
        """Fetch a feed with an explicit timeout so update loops cannot hang indefinitely."""
        feed = NYCTFeed(line_id, fetch_immediately=False)
        feed_url = NYCTFeed._train_to_url.get(line_id, line_id)
        response = requests.get(feed_url, timeout=self.request_timeout_seconds)
        response.raise_for_status()
        feed.load_gtfs_bytes(response.content)
        return feed
    
    def subscribe(self, callback: Callable[[SubwayResult], None]):
        """Subscribe to train updates"""
        self._subscribers.append(callback)
        if self._current_result is not None:  # Send current data to new subscriber
            callback(self._current_result)
    
    def start_updates(self, interval_seconds: int = 15):  # Default 15 seconds
        """Start periodic updates"""
        if self._update_thread and self._update_thread.is_alive():
            logger.warning("Update thread already running")
            return
            
        self._should_run = True
        self._stop_event.clear()
        self._update_thread = threading.Thread(target=self._update_loop, args=(interval_seconds,))
        self._update_thread.daemon = True
        self._update_thread.start()
        logger.info(f"Started subway update thread with {interval_seconds}s interval")
    
    def stop_updates(self):
        """Stop periodic updates"""
        self._should_run = False
        self._stop_event.set()
        if self._update_thread:
            self._update_thread.join()
            self._update_thread = None
        logger.info("Stopped subway updates")
    
    def _should_notify(self, new_result: SubwayResult) -> bool:
        """Determine if we should notify subscribers based on changes"""
        if self._current_result is None:
            return True

        # Availability transitions (e.g. into/out of "service unavailable", or a
        # single line going down) are always worth a refresh.
        if new_result.unavailable_lines != self._current_result.unavailable_lines:
            return True

        new_trains = new_result.trains
        old_trains = self._current_result.trains
        if not old_trains or not new_trains:
            return bool(old_trains) != bool(new_trains)

        # Always notify if first or second train changed
        for i in range(min(2, len(new_trains))):
            if i >= len(old_trains):
                return True
            if new_trains[i] != old_trains[i]:
                return True

        return False

    def _update_loop(self, interval_seconds: int):
        """Background update loop"""
        while self._should_run:
            try:
                new_result = self.get_upcoming_trains()
                should_notify = self._should_notify(new_result)
                self._current_result = new_result
                if should_notify:
                    self._notify_subscribers(new_result)
                if self._stop_event.wait(interval_seconds):
                    break
            except Exception as e:
                logger.error(f"Error in update loop: {str(e)}")
                if self._stop_event.wait(interval_seconds):
                    break

    def _notify_subscribers(self, result: SubwayResult):
        """Notify all subscribers of new train data"""
        for subscriber in self._subscribers:
            try:
                subscriber(result)
            except Exception as e:
                logger.error(f"Error notifying subscriber: {str(e)}")
    
    def get_upcoming_trains(self) -> SubwayResult:
        """Get a snapshot of upcoming trains for the configured station.

        Each configured line feed is fetched independently so that one feed
        failing does not discard data from the other; the returned result
        records which line feeds were unreachable.
        """
        logger.debug(f"Fetching train data for station {self.station_id}")

        arrivals: List[TrainArrival] = []
        unavailable: set[str] = set()

        for line_id in (config.TRAIN_LINE_1, config.TRAIN_LINE_2):
            try:
                feed = self._fetch_feed(line_id)
            except Exception as e:
                logger.error(f"Error fetching feed for line {line_id}: {str(e)}")
                unavailable.add(line_id)
                continue

            trains = feed.filter_trips(headed_for_stop_id=self.station_id)
            logger.info(f"Found {len(trains)} trains for line {line_id}")
            for train in trains:
                arrival = self._process_train(train)
                if arrival:
                    arrivals.append(arrival)
                else:
                    logger.warning(f"Could not process train: {train}")

        sorted_arrivals = sorted(arrivals, key=lambda x: x.minutes_until_arrival)
        if unavailable:
            logger.warning(f"Line feeds unreachable: {sorted(unavailable)}")
        logger.info(f"Returning {len(sorted_arrivals)} processed train arrivals")
        return SubwayResult(trains=sorted_arrivals, unavailable_lines=frozenset(unavailable))
    
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

            logger.info(f"[SUBWAY CALC] Arrival time: {arrival_time.strftime('%I:%M %p')}, Current time: {now.strftime('%I:%M %p')}, Minutes: {minutes}")
            
            return TrainArrival(
                minutes_until_arrival=minutes,
                arrival_time=arrival_time.strftime("%I:%M %p"),
                arrival_timestamp=arrival_time.timestamp(),
                train_id=train.trip_id,
                route_id=train.route_id
            )
            
        except Exception as e:
            logger.error(f"Error processing train: {str(e)}", exc_info=True)
            return None

# Create a global subway service instance
subway_service = SubwayService()
