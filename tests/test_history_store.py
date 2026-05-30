"""Unit tests for services.history_store (SQLite logging + combined join rows).

Run from the repo root:
    uv run python -m unittest tests.test_history_store
"""

import os
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("STATION_ID", "F20S")
os.environ.setdefault("TRAIN_LINE_1", "F")
os.environ.setdefault("TRAIN_LINE_2", "G")
os.environ.setdefault("CITIBIKE_STATION_ID", "test-station-uuid")
os.environ.setdefault("CITIBIKE_STATION_NAME", "Test Station")
os.environ.setdefault("DATA_COLLECTION_ENABLED", "false")

from services.citibike_service import BikeAvailability  # noqa: E402
from services.history_store import HistoryStore  # noqa: E402
from services.subway_service import TrainArrival  # noqa: E402

WEATHER_SAMPLE = {
    "current": {
        "temp_f": 55.0,
        "wind_mph": 8.0,
        "chance_of_rain": 20,
        "chance_of_snow": 0,
        "is_day": 1,
        "condition": {"code": 1003, "text": "Partly cloudy"},
    }
}


def _train(route_id, minutes, train_id):
    return TrainArrival(
        minutes_until_arrival=minutes,
        arrival_time="12:00",
        arrival_timestamp=1700000000.0 + minutes * 60,
        train_id=train_id,
        route_id=route_id,
    )


class HistoryStoreTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        db_path = os.path.join(self.tmpdir.name, "history.db")
        self.store = HistoryStore(
            db_path=db_path,
            station_id="F20S",
            timezone_name="America/New_York",
            bucket_minutes=5,
        )
        self.db_path = db_path

    def tearDown(self):
        self.store.close()
        self.tmpdir.cleanup()

    def _query(self, sql, params=()):
        # Open a fresh read connection so we see committed rows.
        conn = sqlite3.connect(self.db_path)
        try:
            return conn.execute(sql, params).fetchall()
        finally:
            conn.close()

    def test_schema_creates_expected_tables(self):
        rows = self._query(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        )
        names = {r[0] for r in rows}
        for table in (
            "weather_observations",
            "bike_observations",
            "train_snapshots",
            "train_arrivals",
            "combined_observations",
        ):
            self.assertIn(table, names)

    def test_record_weather(self):
        row_id = self.store.record_weather(WEATHER_SAMPLE)
        self.assertGreater(row_id, 0)

        rows = self._query(
            "SELECT temperature_f, condition_code, condition_text "
            "FROM weather_observations WHERE id = ?",
            (row_id,),
        )
        self.assertEqual(len(rows), 1)
        temp_f, code, text = rows[0]
        self.assertEqual(temp_f, 55.0)
        self.assertEqual(code, 1003)
        self.assertEqual(text, "Partly cloudy")

    def test_record_bike(self):
        avail = BikeAvailability(
            classic_bikes=9,
            ebikes=3,
            station_id="test-station-uuid",
            station_name="Test Station",
        )
        row_id = self.store.record_bike(avail)
        self.assertGreater(row_id, 0)

        rows = self._query(
            "SELECT classic_bikes, ebikes, station_name "
            "FROM bike_observations WHERE id = ?",
            (row_id,),
        )
        self.assertEqual(rows[0], (9, 3, "Test Station"))

    def test_record_train_snapshot_writes_snapshot_and_arrivals(self):
        trains = [_train("F", 3, "F-1"), _train("G", 8, "G-1")]
        snapshot_id = self.store.record_train_snapshot(trains)
        self.assertGreater(snapshot_id, 0)

        snap = self._query(
            "SELECT total_trains, station_id FROM train_snapshots WHERE id = ?",
            (snapshot_id,),
        )
        self.assertEqual(snap[0], (2, "F20S"))

        arrivals = self._query(
            "SELECT route_id, minutes_until_arrival FROM train_arrivals "
            "WHERE snapshot_id = ? ORDER BY position",
            (snapshot_id,),
        )
        self.assertEqual(arrivals, [("F", 3), ("G", 8)])

    def test_record_train_snapshot_empty_list(self):
        snapshot_id = self.store.record_train_snapshot([])
        self.assertGreater(snapshot_id, 0)
        arrivals = self._query(
            "SELECT COUNT(*) FROM train_arrivals WHERE snapshot_id = ?",
            (snapshot_id,),
        )
        self.assertEqual(arrivals[0][0], 0)

    def test_record_combined_observation_derives_summary_fields(self):
        avail = BikeAvailability(
            classic_bikes=4,
            ebikes=2,
            station_id="test-station-uuid",
            station_name="Test Station",
        )
        trains = [_train("F", 5, "F-1"), _train("G", 11, "G-1")]
        row_id = self.store.record_combined_observation(
            event_source="test",
            weather_data=WEATHER_SAMPLE,
            bike_data=avail,
            trains=trains,
        )
        self.assertGreater(row_id, 0)

        rows = self._query(
            "SELECT event_source, next_train_minutes, next_f_train_minutes, "
            "next_g_train_minutes, train_count, classic_bikes, ebikes, "
            "total_bikes, temperature_f FROM combined_observations WHERE id = ?",
            (row_id,),
        )
        (
            event_source,
            next_train,
            next_f,
            next_g,
            train_count,
            classic,
            ebikes,
            total,
            temp_f,
        ) = rows[0]
        self.assertEqual(event_source, "test")
        self.assertEqual(next_train, 5)
        self.assertEqual(next_f, 5)
        self.assertEqual(next_g, 11)
        self.assertEqual(train_count, 2)
        self.assertEqual(classic, 4)
        self.assertEqual(ebikes, 2)
        self.assertEqual(total, 6)
        self.assertEqual(temp_f, 55.0)

    def test_record_combined_observation_handles_missing_inputs(self):
        row_id = self.store.record_combined_observation(event_source="empty")
        rows = self._query(
            "SELECT train_count, total_bikes, next_train_minutes "
            "FROM combined_observations WHERE id = ?",
            (row_id,),
        )
        train_count, total_bikes, next_train = rows[0]
        self.assertEqual(train_count, 0)
        self.assertIsNone(total_bikes)
        self.assertIsNone(next_train)


if __name__ == "__main__":
    unittest.main()
