"""Deterministic, hand-written fixture builders for golden-view rendering.

Everything here is a pure function of explicit inputs plus a single fixed
reference time (`FIXED_NOW`). The render path (`ui.layout.getImage`) takes
`now` as a parameter, so passing `FIXED_NOW` makes every rendered pixel
reproducible without freezing the system clock.

Weather payloads mirror the shape produced by `WeatherService.get_weather`:
a `current` dict, a `forecast.forecastday[]` list, and raw `hourly` arrays
that are hour-aligned from midnight (index i == hour-of-day for day 0).
"""

from datetime import datetime, timedelta
import json
from pathlib import Path
from typing import List, Optional

import clock
from config.config import config
from data.models import BirdObservation, BirdResult
from services.subway_service import TrainArrival
from services.citibike_service import BikeAvailability
from services.weather_service import (
    condition_text,
    map_condition_code,
    split_precipitation_chances,
)

# Fixed reference instant for all golden renders: a Thursday afternoon.
FIXED_NOW: datetime = clock.NY_TZ.localize(datetime(2026, 1, 15, 14, 23, 0))

# Number of hourly samples to generate (3 days, matching forecast_days=3).
_HOURLY_SPAN = 72

# A few WMO codes used by scenarios, for readability.
CODE_CLEAR = 0
CODE_PARTLY = 2
CODE_OVERCAST = 3
CODE_FOG = 45
CODE_LIGHT_RAIN = 61
CODE_HEAVY_RAIN = 65
CODE_LIGHT_SNOW = 71
CODE_HEAVY_SNOW = 75
CODE_THUNDERSTORM = 95


def _midnight(now: datetime) -> datetime:
    """Midnight (00:00) of the fixture day, naive (matches Open-Meteo local time)."""
    return datetime(now.year, now.month, now.day, 0, 0, 0)


def make_weather(
    now: datetime = FIXED_NOW,
    *,
    current_temp: float = 38,
    current_code: int = CODE_CLEAR,
    current_wind: float = 6,
    current_precip: int = 0,
    is_day: int = 1,
    hourly_temp: float = 36,
    hourly_code: int = CODE_CLEAR,
    hourly_wind: float = 6,
    hourly_precip: int = 0,
    hourly_rain_mm: float = 0.0,
    hourly_snow_cm: float = 0.0,
    daily_high: float = 42,
    daily_low: float = 30,
    daily_precip: int = 10,
    sunrise: str = "2026-01-15T07:16",
    sunset: str = "2026-01-15T16:52",
    empty_hourly: bool = False,
) -> dict:
    """Build a weather payload in the shape `ui.layout` consumes.

    Hourly arrays are constant across the span (controlled by the `hourly_*`
    args); `current` and `daily` are set independently so scenarios can dial in
    specific edge cases (e.g. high wind now, high precip rest-of-day).
    """
    current_rain, current_snow = split_precipitation_chances(
        current_precip, current_code, 0.0, 0.0
    )
    current = {
        "temp_f": current_temp,
        "condition": {
            "text": condition_text(current_code),
            "code": map_condition_code(current_code),
        },
        "wind_mph": current_wind,
        "precip_chance": current_precip,
        "chance_of_rain": current_rain,
        "chance_of_snow": current_snow,
        "is_day": is_day,
    }

    forecast = {
        "forecastday": [
            {
                "date": now.strftime("%Y-%m-%d"),
                "astro": {
                    "sunrise": sunrise,
                    "sunset": sunset,
                },
                "day": {
                    "maxtemp_f": daily_high,
                    "mintemp_f": daily_low,
                    "daily_chance_of_rain": daily_precip,
                    "condition": {
                        "text": condition_text(current_code),
                        "code": map_condition_code(current_code),
                    },
                },
            }
        ]
    }

    if empty_hourly:
        hourly: dict = {}
    else:
        midnight = _midnight(now)
        times = [(midnight + timedelta(hours=i)).strftime("%Y-%m-%dT%H:00") for i in range(_HOURLY_SPAN)]
        # Gentle temp wave so the hourly lane isn't visually flat.
        temps = [round(hourly_temp + 4 * ((i % 24) / 23.0 - 0.5) * 2) for i in range(_HOURLY_SPAN)]
        hourly = {
            "time": times,
            "temperature_2m": temps,
            "precipitation_probability": [hourly_precip] * _HOURLY_SPAN,
            "rain": [hourly_rain_mm] * _HOURLY_SPAN,
            "snowfall": [hourly_snow_cm] * _HOURLY_SPAN,
            "weathercode": [hourly_code] * _HOURLY_SPAN,
            "windspeed_10m": [hourly_wind] * _HOURLY_SPAN,
            "is_day": [1 if 7 <= (i % 24) <= 17 else 0 for i in range(_HOURLY_SPAN)],
        }

    return {"current": current, "forecast": forecast, "hourly": hourly}


def make_birds() -> BirdResult:
    """Load the committed deterministic BirdNET fixture."""
    payload = json.loads(
        (Path(__file__).parents[2] / "assets" / "birds" / "mock_detections.json").read_text()
    )
    return BirdResult(
        observations=[BirdObservation(**row) for row in payload["observations"]],
        window_hours=payload["window_hours"],
    )


def make_train(minutes_from_now: int, route_id: str, now: datetime = FIXED_NOW, *, seq: int = 0) -> TrainArrival:
    """Build a single TrainArrival arriving `minutes_from_now` after `now`."""
    arrival = now + timedelta(minutes=minutes_from_now)
    return TrainArrival(
        minutes_until_arrival=minutes_from_now,
        arrival_time=arrival.strftime("%I:%M %p"),
        arrival_timestamp=arrival.timestamp(),
        train_id=f"{route_id}-{minutes_from_now}-{seq}",
        route_id=route_id,
    )


def make_trains(
    f_minutes: Optional[List[int]] = None,
    g_minutes: Optional[List[int]] = None,
    now: datetime = FIXED_NOW,
) -> List[TrainArrival]:
    """Build a train list from per-line minute offsets, using configured line ids."""
    trains: List[TrainArrival] = []
    for i, m in enumerate(f_minutes or []):
        trains.append(make_train(m, config.TRAIN_LINE_1, now, seq=i))
    for i, m in enumerate(g_minutes or []):
        trains.append(make_train(m, config.TRAIN_LINE_2, now, seq=i))
    return trains


def make_bikes(classic: int, ebikes: int) -> BikeAvailability:
    return BikeAvailability(
        classic_bikes=classic,
        ebikes=ebikes,
        station_id=config.CITIBIKE_STATION_ID,
        station_name=config.CITIBIKE_STATION_NAME,
    )
