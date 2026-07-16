from datetime import datetime

from config.config import config
from services.weather_service import WeatherService
from tests.golden import fixtures as fx
from ui.panes.all_in_one import AllInOnePane


def _pane() -> AllInOnePane:
    return AllInOnePane((0, 0, config.display.WIDTH, config.display.HEIGHT))


def test_forecast_stations_preserve_rain_probability_and_icon_code():
    weather = fx.make_weather(
        current_code=fx.CODE_HEAVY_RAIN,
        current_precip=91,
        hourly_code=fx.CODE_HEAVY_RAIN,
        hourly_precip=78,
        hourly_rain_mm=2.0,
    )

    stations = _pane()._forecast_stations(weather, fx.FIXED_NOW)

    assert stations[0].precipitation == 91
    assert stations[1].precipitation == 78
    assert stations[1].report["chance_of_rain"] == 78
    assert stations[1].report["chance_of_snow"] == 0
    assert stations[1].report["condition"]["text"] == "Heavy rain"


def test_forecast_stations_preserve_snow_probability_and_icon_code():
    weather = fx.make_weather(
        current_code=fx.CODE_HEAVY_SNOW,
        current_precip=84,
        hourly_code=fx.CODE_HEAVY_SNOW,
        hourly_precip=73,
        hourly_snow_cm=1.5,
    )

    stations = _pane()._forecast_stations(weather, fx.FIXED_NOW)

    assert stations[0].precipitation == 84
    assert stations[1].precipitation == 73
    assert stations[1].report["chance_of_rain"] == 0
    assert stations[1].report["chance_of_snow"] == 73
    assert stations[1].report["condition"]["text"] == "Heavy snow"


def test_solar_events_drive_day_twilight_and_night_weights():
    weather = fx.make_weather()
    pane = _pane()
    stations = pane._forecast_stations(weather, fx.FIXED_NOW)
    events = pane._solar_events(weather, fx.FIXED_NOW)

    assert [event.strftime("%H:%M") for event in events] == ["16:52"]
    assert pane._ribbon_width(datetime(2026, 1, 15, 15, 0), stations, events, weather) == 24
    assert pane._ribbon_width(datetime(2026, 1, 15, 16, 40), stations, events, weather) == 12
    assert pane._ribbon_width(datetime(2026, 1, 15, 18, 0), stations, events, weather) == 4


def test_weather_service_keeps_solar_times_in_forecast_days():
    service = WeatherService()
    data = {
        "daily": {
            "time": ["2026-01-15"],
            "weathercode": [2],
            "temperature_2m_max": [42],
            "temperature_2m_min": [30],
            "precipitation_probability_max": [10],
            "sunrise": ["2026-01-15T07:16"],
            "sunset": ["2026-01-15T16:52"],
        },
        "hourly": {
            "time": [f"2026-01-15T{hour:02d}:00" for hour in range(24)],
            "temperature_2m": [38] * 24,
            "precipitation_probability": [0] * 24,
            "rain": [0] * 24,
            "snowfall": [0] * 24,
            "weathercode": [2] * 24,
            "windspeed_10m": [6] * 24,
            "is_day": [1] * 24,
        },
    }

    days = service._get_forecast_days(data)

    assert days[0]["astro"] == {
        "sunrise": "2026-01-15T07:16",
        "sunset": "2026-01-15T16:52",
    }
