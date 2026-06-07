from data import AppData, DataHub
from services.citibike_service import BikeAvailability
from services.subway_service import SubwayResult


class FakeFeed:
    def __init__(self):
        self.subscribers = []
        self.started_intervals = []
        self.stop_count = 0

    def subscribe(self, callback):
        self.subscribers.append(callback)

    def start_updates(self, interval_seconds):
        self.started_intervals.append(interval_seconds)

    def stop_updates(self):
        self.stop_count += 1

    def emit(self, payload):
        for callback in list(self.subscribers):
            callback(payload)


def _bike_availability() -> BikeAvailability:
    return BikeAvailability(
        classic_bikes=4,
        ebikes=1,
        station_id="station",
        station_name="Station",
    )


def test_app_data_stores_optional_payloads():
    weather = {"current": {}}
    subway = SubwayResult(trains=[])
    bikes = _bike_availability()

    data = AppData(weather=weather, subway=subway, bikes=bikes)

    assert data.weather is weather
    assert data.subway is subway
    assert data.bikes is bikes
    assert data.has("weather")
    assert data.has("subway")
    assert data.has("bikes")


def test_data_hub_updates_each_payload_and_notifies():
    hub = DataHub()
    seen = []
    hub.subscribe(lambda key, data: seen.append((key, data)))

    weather = {"current": {}}
    subway = SubwayResult(trains=[])
    bikes = _bike_availability()

    hub.handle_weather_update(weather)
    hub.handle_subway_update(subway)
    hub.handle_bike_update(bikes)

    assert hub.data == AppData(weather=weather, subway=subway, bikes=bikes)
    assert [key for key, _ in seen] == ["weather", "subway", "bikes"]
    assert seen[-1][1] == hub.data


def test_data_hub_start_subscribes_and_starts_all_feeds():
    weather = FakeFeed()
    subway = FakeFeed()
    bikes = FakeFeed()
    hub = DataHub(weather_feed=weather, subway_feed=subway, bikes_feed=bikes)

    hub.start()

    assert len(weather.subscribers) == 1
    assert len(subway.subscribers) == 1
    assert len(bikes.subscribers) == 1
    assert len(weather.started_intervals) == 1
    assert len(subway.started_intervals) == 1
    assert len(bikes.started_intervals) == 1


def test_data_hub_stop_stops_all_feeds():
    weather = FakeFeed()
    subway = FakeFeed()
    bikes = FakeFeed()
    hub = DataHub(weather_feed=weather, subway_feed=subway, bikes_feed=bikes)

    hub.stop()

    assert weather.stop_count == 1
    assert subway.stop_count == 1
    assert bikes.stop_count == 1


def test_data_hub_feed_emissions_update_app_data():
    weather = FakeFeed()
    subway = FakeFeed()
    bikes = FakeFeed()
    hub = DataHub(weather_feed=weather, subway_feed=subway, bikes_feed=bikes)
    hub.start()

    weather_payload = {"current": {}}
    subway_payload = SubwayResult(trains=[])
    bikes_payload = _bike_availability()

    weather.emit(weather_payload)
    subway.emit(subway_payload)
    bikes.emit(bikes_payload)

    assert hub.data == AppData(
        weather=weather_payload,
        subway=subway_payload,
        bikes=bikes_payload,
    )
