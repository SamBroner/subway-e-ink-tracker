import logging
from typing import Dict, Callable, List
import threading
import requests
from datetime import datetime, timedelta

import clock
from config.config import config
from services.weather_codes import RAIN_WMO_CODES, SNOW_WMO_CODES

logger = logging.getLogger(__name__)

# Mapping of WMO weather codes to WeatherAPI condition codes
_WMO_TO_CONDITION_CODE = {
    0: 1000,   # Clear sky
    1: 1003,   # Mainly clear
    2: 1003,   # Partly cloudy
    3: 1006,   # Overcast
    45: 1135,  # Foggy
    48: 1147,  # Depositing rime fog
    51: 1150,  # Light drizzle
    53: 1153,  # Moderate drizzle
    55: 1153,  # Dense drizzle
    61: 1180,  # Slight rain
    63: 1183,  # Moderate rain
    65: 1186,  # Heavy rain
    71: 1210,  # Slight snow
    73: 1213,  # Moderate snow
    75: 1216,  # Heavy snow
    77: 1255,  # Snow grains
    80: 1240,  # Slight rain showers
    81: 1243,  # Moderate rain showers
    82: 1246,  # Violent rain showers
    85: 1255,  # Slight snow showers
    86: 1258,  # Heavy snow showers
    95: 1273,  # Thunderstorm
    96: 1276,  # Thunderstorm with slight hail
    99: 1279,  # Thunderstorm with heavy hail
}

_WMO_TO_CONDITION_TEXT = {
    0: "Clear",
    1: "Mainly clear",
    2: "Partly cloudy",
    3: "Overcast",
    45: "Foggy",
    48: "Rime fog",
    51: "Light drizzle",
    53: "Moderate drizzle",
    55: "Dense drizzle",
    61: "Light rain",
    63: "Moderate rain",
    65: "Heavy rain",
    71: "Light snow",
    73: "Moderate snow",
    75: "Heavy snow",
    77: "Snow grains",
    80: "Light rain showers",
    81: "Moderate rain showers",
    82: "Violent rain showers",
    85: "Light snow showers",
    86: "Heavy snow showers",
    95: "Thunderstorm",
    96: "Thunderstorm with hail",
    99: "Thunderstorm with heavy hail",
}


def map_condition_code(wmo_code: int) -> int:
    """Map a WMO weather code to a WeatherAPI condition code."""
    return _WMO_TO_CONDITION_CODE.get(wmo_code, 1000)  # Default to clear sky


def condition_text(wmo_code: int) -> str:
    """Convert a WMO weather code to readable condition text."""
    return _WMO_TO_CONDITION_TEXT.get(wmo_code, "Clear")


def split_precipitation_chances(
    precip_probability: float | int,
    weather_code: int,
    rain_mm: float | int,
    snowfall_cm: float | int
) -> tuple[int, int]:
    """Split a generic precip probability into (rain, snow) channels for the UI."""
    precip_probability = int(max(0, min(100, round(float(precip_probability)))))
    rain_mm = float(rain_mm)
    snowfall_cm = float(snowfall_cm)

    has_rain_signal = rain_mm > 0
    has_snow_signal = snowfall_cm > 0

    # Model output can include probability without a non-zero hourly amount due
    # to rounding; fall back to inferring the type from the weather code.
    if not has_rain_signal and not has_snow_signal:
        has_snow_signal = weather_code in SNOW_WMO_CODES
        has_rain_signal = weather_code in RAIN_WMO_CODES

    if has_rain_signal and has_snow_signal:
        return precip_probability, precip_probability
    if has_snow_signal:
        return 0, precip_probability
    if has_rain_signal:
        return precip_probability, 0
    return 0, 0


def build_next_hours_forecast(weather_data: Dict, now: datetime, hours: int = 12) -> List[dict]:
    """Build the next ``hours`` of hourly forecast rows from a weather payload.

    Pure function of (weather_data, now): the hourly slice starts at ``now.hour``
    into the payload's hourly arrays. Returns [] if the payload lacks hourly data.
    """
    hourly = weather_data.get('hourly') if weather_data else None
    if not hourly:
        return []

    times = hourly.get('time', [])
    rain_series = hourly.get('rain', [])
    snowfall_series = hourly.get('snowfall', [])

    current_hour = now.hour
    result: List[dict] = []
    for i in range(current_hour, current_hour + hours):
        if i >= len(times):
            break

        weather_code = hourly['weathercode'][i]
        precip_probability = hourly['precipitation_probability'][i]
        rain_mm = rain_series[i] if i < len(rain_series) else 0
        snowfall_cm = snowfall_series[i] if i < len(snowfall_series) else 0
        chance_of_rain, chance_of_snow = split_precipitation_chances(
            precip_probability=precip_probability,
            weather_code=weather_code,
            rain_mm=rain_mm,
            snowfall_cm=snowfall_cm
        )

        result.append({
            'time': times[i],
            'temp_f': hourly['temperature_2m'][i],
            'chance_of_precipitation': precip_probability,
            'chance_of_rain': chance_of_rain,
            'chance_of_snow': chance_of_snow,
            'rain_mm': rain_mm,
            'snowfall_cm': snowfall_cm,
            'wind_mph': hourly['windspeed_10m'][i],
            'condition': {
                'text': condition_text(weather_code),
                'code': map_condition_code(weather_code)
            },
            'is_day': hourly['is_day'][i]
        })

    return result


class WeatherService:
    def __init__(self):
        self._subscribers: List[Callable[[Dict], None]] = []
        self._update_thread: threading.Thread | None = None
        self._should_run = False
        self._stop_event = threading.Event()
        self._current_data: Dict | None = None
        self.request_timeout_seconds = 10
        self.initial_retry_seconds = 15
    
    def subscribe(self, callback: Callable[[Dict], None]):
        """Subscribe to weather updates"""
        self._subscribers.append(callback)
        if self._current_data:  # Send current data to new subscriber
            callback(self._current_data)
    
    def start_updates(self, interval_seconds: int = 300):  # Default 5 minutes
        """Start periodic updates"""
        if self._update_thread and self._update_thread.is_alive():
            logger.warning("Weather update thread already running")
            return
        
        self._should_run = True
        self._stop_event.clear()
        self._update_thread = threading.Thread(target=self._update_loop, args=(interval_seconds,))
        self._update_thread.daemon = True
        self._update_thread.start()
        logger.info(f"Started weather update thread with {interval_seconds}s interval")
    
    def stop_updates(self):
        """Stop periodic updates"""
        self._should_run = False
        self._stop_event.set()
        if self._update_thread:
            self._update_thread.join()
            self._update_thread = None
        logger.info("Stopped weather updates")

    def _retry_delay_after_error(self, interval_seconds: int) -> int:
        if self._current_data is None:
            return min(interval_seconds, self.initial_retry_seconds)
        return interval_seconds

    def _publish_if_changed(self, weather_data: Dict) -> bool:
        changed = weather_data != self._current_data
        logger.debug(
            "Weather update comparison result: changed=%s (new_type=%s, cache_type=%s)",
            changed,
            type(weather_data).__name__,
            type(self._current_data).__name__ if self._current_data is not None else None,
        )
        if changed:
            self._current_data = weather_data
            self._notify_subscribers(weather_data)
        else:
            logger.debug("Weather data unchanged; skipping subscriber notification")
        return changed

    def _unavailable_result(self) -> Dict | None:
        """Keep the last forecast while explicitly marking it as stale."""
        if self._current_data is None:
            return None
        return {**self._current_data, "source_unavailable": True}

    def _update_loop(self, interval_seconds: int):
        """Background update loop"""
        while self._should_run:
            try:
                weather_data = self.get_weather()
                self._publish_if_changed(weather_data)
                if self._stop_event.wait(interval_seconds):
                    break
            except Exception as e:
                logger.error(f"Error in weather update loop: {str(e)}")
                unavailable = self._unavailable_result()
                if unavailable is not None:
                    self._publish_if_changed(unavailable)
                retry_delay = self._retry_delay_after_error(interval_seconds)
                logger.info("Retrying weather update in %ss", retry_delay)
                if self._stop_event.wait(retry_delay):
                    break
    
    def _notify_subscribers(self, weather_data: Dict):
        """Notify all subscribers of new weather data"""
        for subscriber in self._subscribers:
            try:
                subscriber(weather_data)
            except Exception as e:
                logger.error(f"Error notifying weather subscriber: {str(e)}")

    def _get_commute_forecasts(self, weather_data: Dict) -> List[Dict]:
        """Extract weather forecasts for commute periods"""
        forecasts = []
        ny_tz = clock.NY_TZ
        now = datetime.now(ny_tz)
        
        logger.debug("Starting commute forecast generation")
        logger.debug(f"Daily data structure: {weather_data.get('daily', {}).keys()}")
        
        # Process each commute period for today and tomorrow
        for day_offset in [0, 1]:  # 0 for today, 1 for tomorrow
            target_date = now.date() + timedelta(days=day_offset)
            logger.debug(f"Processing forecasts for date: {target_date}")
            
            # Find the index for this date in the daily data
            try:
                date_str = target_date.strftime('%Y-%m-%d')
                day_index = weather_data['daily']['time'].index(date_str)
                logger.debug(f"Found date {date_str} at index {day_index}")
            except (ValueError, KeyError) as e:
                logger.warning(f"Could not find date {date_str} in daily data: {e}")
                continue
            
            # Process each commute period for this day
            for period, times in config.commute_times.items():
                start_time = datetime.strptime(times['start'], '%H:%M').time()
                end_time = datetime.strptime(times['end'], '%H:%M').time()
                
                # Skip if we're past this period today
                if day_offset == 0 and now.time() > end_time:
                    logger.debug(f"Skipping past period {period} for today")
                    continue
                
                # Find relevant hourly forecasts for this period
                period_indices = []
                for i, timestamp in enumerate(weather_data['hourly']['time']):
                    dt = datetime.fromisoformat(timestamp).astimezone(ny_tz)
                    if dt.date() == target_date and start_time <= dt.time() <= end_time:
                        period_indices.append(i)
                
                if period_indices:
                    logger.debug(f"Found {len(period_indices)} hourly forecasts for period {period}")
                    
                    # Calculate averages for the period
                    temps = [weather_data['hourly']['temperature_2m'][i] for i in period_indices]
                    precip_probs = [weather_data['hourly']['precipitation_probability'][i] for i in period_indices]
                    wind_speeds = [weather_data['hourly']['windspeed_10m'][i] for i in period_indices]
                    weather_codes = [weather_data['hourly']['weathercode'][i] for i in period_indices]
                    
                    avg_temp = sum(temps) / len(temps)
                    max_precip = max(precip_probs)
                    avg_wind = sum(wind_speeds) / len(wind_speeds)
                    
                    # Use middle period weather code for conditions
                    mid_code = weather_codes[len(weather_codes)//2]
                    
                    forecasts.append({
                        'period': times['label'],
                        'date': target_date.strftime('%Y-%m-%d'),
                        'start_time': times['start'],
                        'end_time': times['end'],
                        'temperature': round(avg_temp),
                        'conditions': self._get_condition_text(mid_code),
                        'condition_code': self._map_condition_code(mid_code),
                        'precipitation_chance': round(max_precip),
                        'wind_mph': round(avg_wind)
                    })
                    logger.debug(f"Added forecast for {times['label']}: {forecasts[-1]}")
        
        return forecasts

    def _map_condition_code(self, wmo_code: int) -> int:
        """Map WMO weather codes to WeatherAPI condition codes"""
        return map_condition_code(wmo_code)

    def _get_condition_text(self, wmo_code: int) -> str:
        """Convert WMO weather code to readable condition text"""
        return condition_text(wmo_code)

    def _split_precipitation_chances(
        self,
        precip_probability: float | int,
        weather_code: int,
        rain_mm: float | int,
        snowfall_cm: float | int
    ) -> tuple[int, int]:
        """Split generic precip probability into rain/snow channels for UI rendering."""
        return split_precipitation_chances(
            precip_probability, weather_code, rain_mm, snowfall_cm
        )

    def get_weather(self) -> Dict:
        """Fetch current weather data and add commute forecasts"""
        try:
            # Get coordinates from config
            lat, lon = config.WEATHER_COORDS
            logger.info(f"Fetching weather for coordinates: {lat}, {lon}")
            
            # Construct Open-Meteo API URL
            url = "https://api.open-meteo.com/v1/forecast"
            params = {
                "latitude": lat,
                "longitude": lon,
                "hourly": [
                    "temperature_2m",
                    "precipitation_probability",
                    "rain",
                    "snowfall",
                    "weathercode",
                    "windspeed_10m",
                    "is_day"
                ],
                "daily": [
                    "weathercode",
                    "temperature_2m_max",
                    "temperature_2m_min",
                    "precipitation_probability_max"
                ],
                "timezone": clock.TZ_NAME,
                "temperature_unit": "fahrenheit",
                "windspeed_unit": "mph",
                "forecast_days": 3
            }
            
            logger.debug(f"Making API request to: {url}")
            logger.debug(f"With parameters: {params}")
            
            response = requests.get(url, params=params, timeout=self.request_timeout_seconds)
            response.raise_for_status()
            data = response.json()
            # Transform the data to match our expected format
            weather_data = {
                'source_unavailable': False,
                'current': self._get_current_conditions(data),
                'forecast': {
                    'forecastday': self._get_forecast_days(data)
                },
                'hourly': data['hourly'],
                'commute_forecasts': self._get_commute_forecasts(data)
            }
            
            return weather_data
            
        except Exception as e:
            logger.error(f"Error fetching weather: {str(e)}")
            logger.error(f"Full traceback:", exc_info=True)
            raise

    def _get_current_conditions(self, data: Dict) -> Dict:
        """Extract current conditions from Open-Meteo data"""
        try:
            # Find the index for the current hour
            ny_tz = clock.NY_TZ
            now = datetime.now(ny_tz)
            current_time = now.strftime('%Y-%m-%dT%H:00')
            
            logger.debug(f"Looking for current time: {current_time}")
            logger.debug(f"Available times: {data.get('hourly', {}).get('time', [])[:5]}")
            
            try:
                current_idx = data['hourly']['time'].index(current_time)
                logger.debug(f"Found current time at index: {current_idx}")
            except ValueError:
                logger.warning(f"Could not find exact time {current_time} in hourly data, using first available hour")
                current_idx = 0
            
            # Log the data we're trying to access
            logger.debug(f"Temperature data type: {type(data['hourly']['temperature_2m'])}")
            logger.debug(f"Temperature data length: {len(data['hourly']['temperature_2m'])}")
            logger.debug(f"Current index: {current_idx}")
            
            conditions = {
                'chance_of_rain': 0,
                'chance_of_snow': 0,
                'temp_f': data['hourly']['temperature_2m'][current_idx],
                'condition': {
                    'text': self._get_condition_text(data['hourly']['weathercode'][current_idx]),
                    'code': self._map_condition_code(data['hourly']['weathercode'][current_idx])
                },
                'wind_mph': data['hourly']['windspeed_10m'][current_idx],
                'precip_chance': data['hourly']['precipitation_probability'][current_idx],
                'is_day': data['hourly']['is_day'][current_idx]
            }

            rain_series = data['hourly'].get('rain', [])
            snowfall_series = data['hourly'].get('snowfall', [])
            rain_mm = rain_series[current_idx] if current_idx < len(rain_series) else 0
            snowfall_cm = snowfall_series[current_idx] if current_idx < len(snowfall_series) else 0

            chance_of_rain, chance_of_snow = self._split_precipitation_chances(
                precip_probability=conditions['precip_chance'],
                weather_code=data['hourly']['weathercode'][current_idx],
                rain_mm=rain_mm,
                snowfall_cm=snowfall_cm
            )
            conditions['chance_of_rain'] = chance_of_rain
            conditions['chance_of_snow'] = chance_of_snow
            
            logger.debug(f"Generated current conditions: {conditions}")
            return conditions
            
        except Exception as e:
            logger.error(f"Error in _get_current_conditions: {str(e)}")
            logger.error("Data structure received:", data)
            logger.error(f"Full traceback:", exc_info=True)
            raise

    def _get_forecast_days(self, data: Dict) -> List[Dict]:
        """Transform daily forecast data to match expected format"""
        forecasts = []
        for i in range(len(data['daily']['time'])):
            forecasts.append({
                'date': data['daily']['time'][i],
                'day': {
                    'maxtemp_f': data['daily']['temperature_2m_max'][i],
                    'mintemp_f': data['daily']['temperature_2m_min'][i],
                    'daily_chance_of_rain': data['daily']['precipitation_probability_max'][i],
                    'condition': {
                        'text': self._get_condition_text(data['daily']['weathercode'][i]),
                        'code': self._map_condition_code(data['daily']['weathercode'][i])
                    }
                },
                'hour': self._get_hourly_data_for_day(data, i)
            })
        return forecasts

    def _get_hourly_data_for_day(self, data: Dict, day_index: int) -> List[Dict]:
        """Extract hourly data for a specific day"""
        start_idx = day_index * 24
        end_idx = start_idx + 24
        
        hourly_data = []
        for i in range(start_idx, end_idx):
            weather_code = data['hourly']['weathercode'][i]
            precip_probability = data['hourly']['precipitation_probability'][i]
            rain_series = data['hourly'].get('rain', [])
            snowfall_series = data['hourly'].get('snowfall', [])
            rain_mm = rain_series[i] if i < len(rain_series) else 0
            snowfall_cm = snowfall_series[i] if i < len(snowfall_series) else 0
            chance_of_rain, chance_of_snow = self._split_precipitation_chances(
                precip_probability=precip_probability,
                weather_code=weather_code,
                rain_mm=rain_mm,
                snowfall_cm=snowfall_cm
            )

            hourly_data.append({
                'time': data['hourly']['time'][i],
                'temp_f': data['hourly']['temperature_2m'][i],
                'chance_of_precipitation': precip_probability,
                'chance_of_rain': chance_of_rain,
                'chance_of_snow': chance_of_snow,
                'rain_mm': rain_mm,
                'snowfall_cm': snowfall_cm,
                'wind_mph': data['hourly']['windspeed_10m'][i],
                'condition': {
                    'text': self._get_condition_text(weather_code),
                    'code': self._map_condition_code(weather_code)
                },
                'is_day': data['hourly']['is_day'][i]
            })
        return hourly_data

    def get_next_commutes(self, include_today: bool = True) -> List[Dict]:
        """Get the next commute period forecasts"""
        if not self._current_data:
            logger.warning("No current weather data available for commute forecasts")
            return []
        
        try:
            # If we have commute forecasts in the current data, use those
            if 'commute_forecasts' in self._current_data:
                forecasts = self._current_data['commute_forecasts']
                if not include_today:
                    # Filter out today's forecasts if not requested
                    today = datetime.now(clock.NY_TZ).strftime('%Y-%m-%d')
                    forecasts = [f for f in forecasts if f['date'] != today]
                return forecasts
            
            # Otherwise, generate them from the current data
            logger.debug("Generating commute forecasts from current data")
            return self._get_commute_forecasts(self._current_data)
            
        except Exception as e:
            logger.error(f"Error getting commute forecasts: {e}")
            logger.debug("Current data structure:", self._current_data)
            return []

# Create a global weather service instance
weather_service = WeatherService() 
