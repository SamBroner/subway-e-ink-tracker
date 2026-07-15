import logging
import threading
from typing import Callable

from config.config import config
from data.models import AppData, BirdResult, DataKey, WeatherPayload
from services.bird_service import bird_service
from services.citibike_service import BikeAvailability, citibike_service
from services.subway_service import SubwayResult, subway_service
from services.weather_service import weather_service


logger = logging.getLogger(__name__)

DataCallback = Callable[[DataKey, AppData], None]


class DataHub:
    """Owns feed subscriptions and the latest app-data snapshot."""

    def __init__(
        self,
        *,
        initial_data: AppData | None = None,
        weather_feed=weather_service,
        subway_feed=subway_service,
        bikes_feed=citibike_service,
        birds_feed=bird_service,
    ):
        self._data = initial_data or AppData()
        self._weather_feed = weather_feed
        self._subway_feed = subway_feed
        self._bikes_feed = bikes_feed
        self._birds_feed = birds_feed
        self._subscribers: list[DataCallback] = []
        self._lock = threading.Lock()
        self._feeds_subscribed = False
        self._started = False

    @property
    def data(self) -> AppData:
        with self._lock:
            return self._data

    def subscribe(self, callback: DataCallback) -> None:
        self._subscribers.append(callback)

    def start(self) -> None:
        if self._started:
            logger.warning("DataHub already started")
            return

        if not self._feeds_subscribed:
            self._weather_feed.subscribe(self.handle_weather_update)
            self._subway_feed.subscribe(self.handle_subway_update)
            self._bikes_feed.subscribe(self.handle_bike_update)
            self._birds_feed.subscribe(self.handle_bird_update)
            self._feeds_subscribed = True

        self._weather_feed.start_updates(interval_seconds=config.timing.WEATHER_UPDATE_SECONDS)
        self._subway_feed.start_updates(interval_seconds=config.timing.SUBWAY_UPDATE_SECONDS)
        self._bikes_feed.start_updates(interval_seconds=config.timing.CITIBIKE_UPDATE_SECONDS)
        self._birds_feed.start_updates(interval_seconds=config.timing.BIRD_UPDATE_SECONDS)

        self._started = True
        logger.info("Started data hub")

    def stop(self) -> None:
        self._subway_feed.stop_updates()
        self._weather_feed.stop_updates()
        self._bikes_feed.stop_updates()
        self._birds_feed.stop_updates()
        self._started = False
        logger.info("Stopped data hub")

    def handle_weather_update(self, weather: WeatherPayload) -> None:
        self._publish("weather", weather)

    def handle_subway_update(self, subway: SubwayResult) -> None:
        self._publish("subway", subway)

    def handle_bike_update(self, bikes: BikeAvailability) -> None:
        self._publish("bikes", bikes)

    def handle_bird_update(self, birds: BirdResult) -> None:
        self._publish("birds", birds)

    def _publish(self, key: DataKey, value) -> None:
        with self._lock:
            self._data = self._data.with_update(key, value)
            snapshot = self._data

        for subscriber in list(self._subscribers):
            try:
                subscriber(key, snapshot)
            except Exception as e:
                logger.error("Error notifying data subscriber for %s: %s", key, e, exc_info=True)
