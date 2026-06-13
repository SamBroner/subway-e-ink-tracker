import threading
import time
import subprocess

import pytest

from data import BirdObservation, BirdResult
from services.bird_service import BirdService
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


def test_bird_stop_interrupts_interval_sleep():
    service = BirdService()
    first_fetch = threading.Event()

    def fetch_once():
        first_fetch.set()
        return BirdResult(observations=[], window_hours=24)

    service.get_bird_observations = fetch_once

    _assert_stop_interrupts_interval_sleep(service, first_fetch)


def test_bird_service_uses_configured_result_limit(monkeypatch):
    monkeypatch.setattr("services.bird_service.config.BIRD_RESULT_LIMIT", 15)
    service = BirdService()

    assert service.result_limit == 15
    assert "LIMIT 15" in service._summary_query()

    monkeypatch.setattr("services.bird_service.config.BIRD_RESULT_LIMIT", 22)
    assert BirdService().result_limit == 22


def test_bird_summary_query_orders_by_recency_first(monkeypatch):
    monkeypatch.setattr("services.bird_service.config.BIRD_RESULT_LIMIT", 15)
    service = BirdService()

    query = service._summary_query()

    assert "ORDER BY last_seen DESC, count DESC" in query
    assert "ORDER BY count DESC" not in query


def test_bird_service_parses_ssh_sqlite_json(monkeypatch):
    service = BirdService()
    service.ssh_host = "birdnet"
    service.db_path = "~/BirdNET-Pi/scripts/birds.db"
    service.window_hours = 24
    service.use_mock_data = False

    def fake_run(args, **kwargs):
        assert args[:4] == ["ssh", "-o", "BatchMode=yes", "birdnet"]
        assert "sqlite3 -json ~/BirdNET-Pi/scripts/birds.db" in args[4]
        assert "FROM detections" in args[4]
        assert kwargs["timeout"] == service.request_timeout_seconds
        return subprocess.CompletedProcess(
            args=args,
            returncode=0,
            stdout=(
                '[{"sci_name":"Poecile atricapillus",'
                '"common_name":"Black-capped Chickadee",'
                '"count":4,'
                '"last_seen":"2026-06-11 22:40:10",'
                '"max_confidence":0.908}]'
            ),
            stderr="",
        )

    monkeypatch.setattr("services.bird_service.subprocess.run", fake_run)

    assert service.get_bird_observations() == BirdResult(
        observations=[
            BirdObservation(
                sci_name="Poecile atricapillus",
                common_name="Black-capped Chickadee",
                count=4,
                last_seen="2026-06-11 22:40:10",
                max_confidence=0.908,
            )
        ],
        window_hours=24,
    )


def test_bird_service_keeps_last_good_data_on_failure(monkeypatch):
    service = BirdService()
    service.use_mock_data = False
    service._current_result = BirdResult(
        observations=[
            BirdObservation(
                sci_name="Poecile atricapillus",
                common_name="Black-capped Chickadee",
                count=4,
                last_seen="2026-06-11 22:40:10",
                max_confidence=0.908,
            )
        ],
        window_hours=24,
    )

    def fake_run(*_args, **_kwargs):
        raise subprocess.TimeoutExpired(cmd="ssh", timeout=1)

    monkeypatch.setattr("services.bird_service.subprocess.run", fake_run)

    result = service.get_bird_observations()

    assert result.observations == service._current_result.observations
    assert result.window_hours == 24
    assert result.source_unavailable


def _assert_stop_interrupts_interval_sleep(service, first_fetch):
    service.start_updates(interval_seconds=60)
    assert first_fetch.wait(1)

    start = time.monotonic()
    service.stop_updates()
    elapsed = time.monotonic() - start

    assert elapsed < 0.5
    assert service._update_thread is None
