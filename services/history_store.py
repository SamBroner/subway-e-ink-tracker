from __future__ import annotations

import json
import logging
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

if TYPE_CHECKING:
    from services.citibike_service import BikeAvailability
    from services.subway_service import TrainArrival

logger = logging.getLogger(__name__)


class HistoryStore:
    """Durable append-only store for bike, train, and weather observations."""

    def __init__(
        self,
        db_path: str,
        station_id: str,
        timezone_name: str = "America/New_York",
        bucket_minutes: int = 5,
    ):
        self.db_path = Path(db_path)
        self.station_id = station_id
        self.timezone_name = timezone_name
        self.bucket_minutes = max(1, bucket_minutes)
        self._lock = threading.Lock()

        try:
            self._local_timezone = ZoneInfo(self.timezone_name)
        except ZoneInfoNotFoundError:
            logger.warning(
                "Unknown timezone %s; defaulting to UTC for history buckets",
                self.timezone_name,
            )
            self._local_timezone = timezone.utc

        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL;")
        self._conn.execute("PRAGMA synchronous=NORMAL;")
        self._conn.execute("PRAGMA foreign_keys=ON;")
        self._initialize_schema()
        logger.info("History store ready at %s", self.db_path)

    def close(self):
        with self._lock:
            self._conn.close()

    def record_weather(self, weather_data: dict) -> int:
        observed_at = self._utc_now()
        time_parts = self._time_parts(observed_at)
        current = weather_data.get("current", {})
        payload_json = self._to_json(weather_data)

        with self._lock:
            with self._conn:
                cursor = self._conn.execute(
                    """
                    INSERT INTO weather_observations (
                        observed_at_utc,
                        observed_at_epoch,
                        observed_at_local,
                        local_date,
                        local_hour,
                        local_weekday,
                        time_bucket_epoch,
                        time_bucket_local,
                        temperature_f,
                        wind_mph,
                        precip_chance,
                        chance_of_rain,
                        chance_of_snow,
                        condition_code,
                        condition_text,
                        is_day,
                        payload_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        observed_at.isoformat(),
                        time_parts["observed_at_epoch"],
                        time_parts["observed_at_local"],
                        time_parts["local_date"],
                        time_parts["local_hour"],
                        time_parts["local_weekday"],
                        time_parts["time_bucket_epoch"],
                        time_parts["time_bucket_local"],
                        current.get("temp_f"),
                        current.get("wind_mph"),
                        current.get("precip_chance"),
                        current.get("chance_of_rain"),
                        current.get("chance_of_snow"),
                        current.get("condition", {}).get("code"),
                        current.get("condition", {}).get("text"),
                        current.get("is_day"),
                        payload_json,
                    ),
                )
                return int(cursor.lastrowid)

    def record_bike(self, availability: "BikeAvailability") -> int:
        observed_at = self._utc_now()
        time_parts = self._time_parts(observed_at)
        payload_json = self._to_json(
            {
                "classic_bikes": availability.classic_bikes,
                "ebikes": availability.ebikes,
                "station_id": availability.station_id,
                "station_name": availability.station_name,
            }
        )

        with self._lock:
            with self._conn:
                cursor = self._conn.execute(
                    """
                    INSERT INTO bike_observations (
                        observed_at_utc,
                        observed_at_epoch,
                        observed_at_local,
                        local_date,
                        local_hour,
                        local_weekday,
                        time_bucket_epoch,
                        time_bucket_local,
                        station_id,
                        station_name,
                        classic_bikes,
                        ebikes,
                        payload_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        observed_at.isoformat(),
                        time_parts["observed_at_epoch"],
                        time_parts["observed_at_local"],
                        time_parts["local_date"],
                        time_parts["local_hour"],
                        time_parts["local_weekday"],
                        time_parts["time_bucket_epoch"],
                        time_parts["time_bucket_local"],
                        availability.station_id,
                        availability.station_name,
                        availability.classic_bikes,
                        availability.ebikes,
                        payload_json,
                    ),
                )
                return int(cursor.lastrowid)

    def record_train_snapshot(self, trains: list["TrainArrival"]) -> int:
        observed_at = self._utc_now()
        time_parts = self._time_parts(observed_at)

        arrivals_payload = [
            {
                "position": idx,
                "route_id": train.route_id,
                "train_id": train.train_id,
                "minutes_until_arrival": train.minutes_until_arrival,
                "arrival_timestamp": train.arrival_timestamp,
                "arrival_time": train.arrival_time,
            }
            for idx, train in enumerate(trains)
        ]
        payload_json = self._to_json(arrivals_payload)

        with self._lock:
            with self._conn:
                cursor = self._conn.execute(
                    """
                    INSERT INTO train_snapshots (
                        observed_at_utc,
                        observed_at_epoch,
                        observed_at_local,
                        local_date,
                        local_hour,
                        local_weekday,
                        time_bucket_epoch,
                        time_bucket_local,
                        station_id,
                        total_trains,
                        payload_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        observed_at.isoformat(),
                        time_parts["observed_at_epoch"],
                        time_parts["observed_at_local"],
                        time_parts["local_date"],
                        time_parts["local_hour"],
                        time_parts["local_weekday"],
                        time_parts["time_bucket_epoch"],
                        time_parts["time_bucket_local"],
                        self.station_id,
                        len(trains),
                        payload_json,
                    ),
                )
                snapshot_id = cursor.lastrowid

                if trains:
                    self._conn.executemany(
                        """
                        INSERT INTO train_arrivals (
                            snapshot_id,
                            observed_at_utc,
                            observed_at_epoch,
                            observed_at_local,
                            local_date,
                            local_hour,
                            local_weekday,
                            time_bucket_epoch,
                            time_bucket_local,
                            position,
                            route_id,
                            train_id,
                            minutes_until_arrival,
                            arrival_timestamp,
                            arrival_time_text
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        [
                            (
                                snapshot_id,
                                observed_at.isoformat(),
                                time_parts["observed_at_epoch"],
                                time_parts["observed_at_local"],
                                time_parts["local_date"],
                                time_parts["local_hour"],
                                time_parts["local_weekday"],
                                time_parts["time_bucket_epoch"],
                                time_parts["time_bucket_local"],
                                idx,
                                train.route_id,
                                train.train_id,
                                train.minutes_until_arrival,
                                train.arrival_timestamp,
                                train.arrival_time,
                            )
                            for idx, train in enumerate(trains)
                        ],
                    )
                return int(snapshot_id)

    def record_combined_observation(
        self,
        event_source: str,
        weather_data: dict | None = None,
        bike_data: "BikeAvailability" | None = None,
        trains: list["TrainArrival"] | None = None,
        weather_observation_id: int | None = None,
        bike_observation_id: int | None = None,
        train_snapshot_id: int | None = None,
    ) -> int:
        observed_at = self._utc_now()
        time_parts = self._time_parts(observed_at)

        current_weather = (weather_data or {}).get("current", {})
        trains = trains or []
        next_train_minutes = trains[0].minutes_until_arrival if trains else None
        next_f_train_minutes = self._next_minutes_for_route(trains, "F")
        next_g_train_minutes = self._next_minutes_for_route(trains, "G")

        classic_bikes = bike_data.classic_bikes if bike_data else None
        ebikes = bike_data.ebikes if bike_data else None
        total_bikes = (
            (classic_bikes or 0) + (ebikes or 0)
            if classic_bikes is not None or ebikes is not None
            else None
        )

        with self._lock:
            with self._conn:
                cursor = self._conn.execute(
                    """
                    INSERT INTO combined_observations (
                        observed_at_utc,
                        observed_at_epoch,
                        observed_at_local,
                        local_date,
                        local_hour,
                        local_weekday,
                        time_bucket_epoch,
                        time_bucket_local,
                        event_source,
                        station_id,
                        weather_observation_id,
                        bike_observation_id,
                        train_snapshot_id,
                        next_train_minutes,
                        next_f_train_minutes,
                        next_g_train_minutes,
                        train_count,
                        classic_bikes,
                        ebikes,
                        total_bikes,
                        temperature_f,
                        wind_mph,
                        precip_chance,
                        chance_of_rain,
                        chance_of_snow,
                        condition_code,
                        condition_text
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        observed_at.isoformat(),
                        time_parts["observed_at_epoch"],
                        time_parts["observed_at_local"],
                        time_parts["local_date"],
                        time_parts["local_hour"],
                        time_parts["local_weekday"],
                        time_parts["time_bucket_epoch"],
                        time_parts["time_bucket_local"],
                        event_source,
                        self.station_id,
                        weather_observation_id,
                        bike_observation_id,
                        train_snapshot_id,
                        next_train_minutes,
                        next_f_train_minutes,
                        next_g_train_minutes,
                        len(trains),
                        classic_bikes,
                        ebikes,
                        total_bikes,
                        current_weather.get("temp_f"),
                        current_weather.get("wind_mph"),
                        current_weather.get("precip_chance"),
                        current_weather.get("chance_of_rain"),
                        current_weather.get("chance_of_snow"),
                        current_weather.get("condition", {}).get("code"),
                        current_weather.get("condition", {}).get("text"),
                    ),
                )
                return int(cursor.lastrowid)

    def _initialize_schema(self):
        with self._lock:
            with self._conn:
                self._conn.executescript(
                    """
                    CREATE TABLE IF NOT EXISTS weather_observations (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        observed_at_utc TEXT NOT NULL,
                        observed_at_epoch INTEGER NOT NULL,
                        observed_at_local TEXT NOT NULL,
                        local_date TEXT NOT NULL,
                        local_hour INTEGER NOT NULL,
                        local_weekday INTEGER NOT NULL,
                        time_bucket_epoch INTEGER NOT NULL,
                        time_bucket_local TEXT NOT NULL,
                        temperature_f REAL,
                        wind_mph REAL,
                        precip_chance INTEGER,
                        chance_of_rain INTEGER,
                        chance_of_snow INTEGER,
                        condition_code INTEGER,
                        condition_text TEXT,
                        is_day INTEGER,
                        payload_json TEXT NOT NULL
                    );

                    CREATE TABLE IF NOT EXISTS bike_observations (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        observed_at_utc TEXT NOT NULL,
                        observed_at_epoch INTEGER NOT NULL,
                        observed_at_local TEXT NOT NULL,
                        local_date TEXT NOT NULL,
                        local_hour INTEGER NOT NULL,
                        local_weekday INTEGER NOT NULL,
                        time_bucket_epoch INTEGER NOT NULL,
                        time_bucket_local TEXT NOT NULL,
                        station_id TEXT NOT NULL,
                        station_name TEXT,
                        classic_bikes INTEGER,
                        ebikes INTEGER,
                        payload_json TEXT NOT NULL
                    );

                    CREATE TABLE IF NOT EXISTS train_snapshots (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        observed_at_utc TEXT NOT NULL,
                        observed_at_epoch INTEGER NOT NULL,
                        observed_at_local TEXT NOT NULL,
                        local_date TEXT NOT NULL,
                        local_hour INTEGER NOT NULL,
                        local_weekday INTEGER NOT NULL,
                        time_bucket_epoch INTEGER NOT NULL,
                        time_bucket_local TEXT NOT NULL,
                        station_id TEXT NOT NULL,
                        total_trains INTEGER NOT NULL,
                        payload_json TEXT NOT NULL
                    );

                    CREATE TABLE IF NOT EXISTS train_arrivals (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        snapshot_id INTEGER NOT NULL,
                        observed_at_utc TEXT NOT NULL,
                        observed_at_epoch INTEGER NOT NULL,
                        observed_at_local TEXT NOT NULL,
                        local_date TEXT NOT NULL,
                        local_hour INTEGER NOT NULL,
                        local_weekday INTEGER NOT NULL,
                        time_bucket_epoch INTEGER NOT NULL,
                        time_bucket_local TEXT NOT NULL,
                        position INTEGER NOT NULL,
                        route_id TEXT,
                        train_id TEXT,
                        minutes_until_arrival INTEGER,
                        arrival_timestamp REAL,
                        arrival_time_text TEXT,
                        FOREIGN KEY (snapshot_id) REFERENCES train_snapshots(id) ON DELETE CASCADE
                    );

                    CREATE TABLE IF NOT EXISTS combined_observations (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        observed_at_utc TEXT NOT NULL,
                        observed_at_epoch INTEGER NOT NULL,
                        observed_at_local TEXT NOT NULL,
                        local_date TEXT NOT NULL,
                        local_hour INTEGER NOT NULL,
                        local_weekday INTEGER NOT NULL,
                        time_bucket_epoch INTEGER NOT NULL,
                        time_bucket_local TEXT NOT NULL,
                        event_source TEXT NOT NULL,
                        station_id TEXT NOT NULL,
                        weather_observation_id INTEGER,
                        bike_observation_id INTEGER,
                        train_snapshot_id INTEGER,
                        next_train_minutes INTEGER,
                        next_f_train_minutes INTEGER,
                        next_g_train_minutes INTEGER,
                        train_count INTEGER,
                        classic_bikes INTEGER,
                        ebikes INTEGER,
                        total_bikes INTEGER,
                        temperature_f REAL,
                        wind_mph REAL,
                        precip_chance INTEGER,
                        chance_of_rain INTEGER,
                        chance_of_snow INTEGER,
                        condition_code INTEGER,
                        condition_text TEXT,
                        FOREIGN KEY (weather_observation_id) REFERENCES weather_observations(id),
                        FOREIGN KEY (bike_observation_id) REFERENCES bike_observations(id),
                        FOREIGN KEY (train_snapshot_id) REFERENCES train_snapshots(id)
                    );

                    CREATE INDEX IF NOT EXISTS idx_weather_observed_epoch
                    ON weather_observations(observed_at_epoch);

                    CREATE INDEX IF NOT EXISTS idx_weather_bucket_epoch
                    ON weather_observations(time_bucket_epoch);

                    CREATE INDEX IF NOT EXISTS idx_weather_local_date_hour
                    ON weather_observations(local_date, local_hour);

                    CREATE INDEX IF NOT EXISTS idx_bike_station_epoch
                    ON bike_observations(station_id, observed_at_epoch);

                    CREATE INDEX IF NOT EXISTS idx_bike_bucket_epoch
                    ON bike_observations(time_bucket_epoch);

                    CREATE INDEX IF NOT EXISTS idx_bike_local_date_hour
                    ON bike_observations(local_date, local_hour);

                    CREATE INDEX IF NOT EXISTS idx_train_snapshots_station_epoch
                    ON train_snapshots(station_id, observed_at_epoch);

                    CREATE INDEX IF NOT EXISTS idx_train_snapshots_bucket_epoch
                    ON train_snapshots(time_bucket_epoch);

                    CREATE INDEX IF NOT EXISTS idx_train_snapshots_local_date_hour
                    ON train_snapshots(local_date, local_hour);

                    CREATE INDEX IF NOT EXISTS idx_train_arrivals_snapshot
                    ON train_arrivals(snapshot_id);

                    CREATE INDEX IF NOT EXISTS idx_train_arrivals_route_epoch
                    ON train_arrivals(route_id, observed_at_epoch);

                    CREATE INDEX IF NOT EXISTS idx_train_arrivals_bucket_epoch
                    ON train_arrivals(time_bucket_epoch);

                    CREATE INDEX IF NOT EXISTS idx_train_arrivals_train_id_epoch
                    ON train_arrivals(train_id, observed_at_epoch);

                    CREATE INDEX IF NOT EXISTS idx_combined_observations_station_epoch
                    ON combined_observations(station_id, observed_at_epoch);

                    CREATE INDEX IF NOT EXISTS idx_combined_observations_bucket
                    ON combined_observations(time_bucket_epoch);

                    CREATE INDEX IF NOT EXISTS idx_combined_observations_local_date_hour
                    ON combined_observations(local_date, local_hour);
                    """
                )

                self._ensure_columns(
                    "weather_observations",
                    {
                        "observed_at_local": "TEXT",
                        "local_date": "TEXT",
                        "local_hour": "INTEGER",
                        "local_weekday": "INTEGER",
                        "time_bucket_epoch": "INTEGER",
                        "time_bucket_local": "TEXT",
                    },
                )
                self._ensure_columns(
                    "bike_observations",
                    {
                        "observed_at_local": "TEXT",
                        "local_date": "TEXT",
                        "local_hour": "INTEGER",
                        "local_weekday": "INTEGER",
                        "time_bucket_epoch": "INTEGER",
                        "time_bucket_local": "TEXT",
                    },
                )
                self._ensure_columns(
                    "train_snapshots",
                    {
                        "observed_at_local": "TEXT",
                        "local_date": "TEXT",
                        "local_hour": "INTEGER",
                        "local_weekday": "INTEGER",
                        "time_bucket_epoch": "INTEGER",
                        "time_bucket_local": "TEXT",
                    },
                )
                self._ensure_columns(
                    "train_arrivals",
                    {
                        "observed_at_local": "TEXT",
                        "local_date": "TEXT",
                        "local_hour": "INTEGER",
                        "local_weekday": "INTEGER",
                        "time_bucket_epoch": "INTEGER",
                        "time_bucket_local": "TEXT",
                    },
                )

    def _ensure_columns(self, table_name: str, required_columns: dict[str, str]):
        existing_columns = {
            row[1] for row in self._conn.execute(f"PRAGMA table_info({table_name})").fetchall()
        }
        for column_name, column_type in required_columns.items():
            if column_name not in existing_columns:
                self._conn.execute(
                    f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type}"
                )

    def _time_parts(self, observed_at_utc: datetime) -> dict[str, int | str]:
        observed_at_epoch = int(observed_at_utc.timestamp())
        observed_at_local = observed_at_utc.astimezone(self._local_timezone)
        bucket_seconds = self.bucket_minutes * 60
        time_bucket_epoch = (observed_at_epoch // bucket_seconds) * bucket_seconds
        time_bucket_local = datetime.fromtimestamp(
            time_bucket_epoch, tz=timezone.utc
        ).astimezone(self._local_timezone)
        return {
            "observed_at_epoch": observed_at_epoch,
            "observed_at_local": observed_at_local.isoformat(),
            "local_date": observed_at_local.date().isoformat(),
            "local_hour": observed_at_local.hour,
            "local_weekday": observed_at_local.weekday(),
            "time_bucket_epoch": time_bucket_epoch,
            "time_bucket_local": time_bucket_local.isoformat(),
        }

    @staticmethod
    def _next_minutes_for_route(trains: list["TrainArrival"], route_id: str) -> int | None:
        for train in trains:
            if train.route_id == route_id:
                return train.minutes_until_arrival
        return None

    @staticmethod
    def _to_json(payload: object) -> str:
        return json.dumps(payload, separators=(",", ":"), sort_keys=True)

    @staticmethod
    def _utc_now() -> datetime:
        return datetime.now(timezone.utc)
