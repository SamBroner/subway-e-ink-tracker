import threading
import time

import pytest

from services.citibike_service import BikeAvailability, CitibikeService
from services.subway_service import SubwayResult, SubwayService
from services.weather_service import WeatherService


def test_weather_request_uses_timeout(monkeypatch):
    service = WeatherService()
    seen_kwargs = {}

    def fake_get(*_args, **kwargs):
        seen_kwargs.update(kwargs)
        raise RuntimeError("network failed")

    monkeypatch.setattr("services.weather_service.requests.get", fake_get)

    with pytest.raises(RuntimeError):
        service.get_weather()

    assert seen_kwargs["timeout"] == service.request_timeout_seconds


def test_weather_initial_failure_uses_short_retry_delay():
    service = WeatherService()
    service.initial_retry_seconds = 15

    assert service._retry_delay_after_error(300) == 15
    assert service._retry_delay_after_error(5) == 5

    service._current_data = {"current": {}}
    assert service._retry_delay_after_error(300) == 300


def test_weather_stop_interrupts_interval_sleep():
    service = WeatherService()
    first_fetch = threading.Event()

    def fetch_once():
        first_fetch.set()
        return {"current": {}}

    service.get_weather = fetch_once

    _assert_stop_interrupts_interval_sleep(service, first_fetch)


def test_subway_stop_interrupts_interval_sleep():
    service = SubwayService()
    first_fetch = threading.Event()

    def fetch_once():
        first_fetch.set()
        return SubwayResult(trains=[])

    service.get_upcoming_trains = fetch_once

    _assert_stop_interrupts_interval_sleep(service, first_fetch)


def test_citibike_stop_interrupts_interval_sleep():
    service = CitibikeService()
    first_fetch = threading.Event()

    def fetch_once():
        first_fetch.set()
        return BikeAvailability(
            classic_bikes=1,
            ebikes=2,
            station_id="station",
            station_name="Station",
        )

    service.get_bike_availability = fetch_once

    _assert_stop_interrupts_interval_sleep(service, first_fetch)


def _assert_stop_interrupts_interval_sleep(service, first_fetch):
    service.start_updates(interval_seconds=60)
    assert first_fetch.wait(1)

    start = time.monotonic()
    service.stop_updates()
    elapsed = time.monotonic() - start

    assert elapsed < 0.5
    assert service._update_thread is None
