"""Unit tests for services.citibike_service (GBFS parsing + change detection).

Run from the repo root:
    uv run python -m unittest tests.test_citibike_service
"""

import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

# Make the package importable when run as a standalone file, and provide env
# defaults so config loads even without a populated config/.env (real values in
# config/.env still win because config loads it with override=True).
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("STATION_ID", "F20S")
os.environ.setdefault("TRAIN_LINE_1", "F")
os.environ.setdefault("TRAIN_LINE_2", "G")
os.environ.setdefault("CITIBIKE_STATION_ID", "test-station-uuid")
os.environ.setdefault("CITIBIKE_STATION_NAME", "Test Station")

from services.citibike_service import (  # noqa: E402
    BikeAvailability,
    CitibikeService,
    config,
)


class FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


def _gbfs_payload(station_id, classic=0, ebikes=0, include=True):
    station = {
        "station_id": station_id,
        "vehicle_types_available": [
            {"vehicle_type_id": "1", "count": classic},
            {"vehicle_type_id": "2", "count": ebikes},
        ],
    }
    stations = [station] if include else []
    return {"data": {"stations": stations}}


class GetBikeAvailabilityTests(unittest.TestCase):
    def setUp(self):
        self.service = CitibikeService()
        self.service.station_id = "test-station-uuid"

    @patch.object(config, "CITIBIKE_STATION_NAME", "Test Station")
    @patch("services.citibike_service.requests.get")
    def test_parses_classic_and_ebike_counts(self, mock_get):
        mock_get.return_value = FakeResponse(
            _gbfs_payload("test-station-uuid", classic=7, ebikes=4)
        )

        result = self.service.get_bike_availability()

        self.assertIsInstance(result, BikeAvailability)
        self.assertEqual(result.classic_bikes, 7)
        self.assertEqual(result.ebikes, 4)
        self.assertEqual(result.station_id, "test-station-uuid")
        self.assertEqual(result.station_name, "Test Station")

    @patch("services.citibike_service.requests.get")
    def test_returns_none_when_station_missing(self, mock_get):
        mock_get.return_value = FakeResponse(
            _gbfs_payload("some-other-station", classic=2, ebikes=1)
        )

        self.assertIsNone(self.service.get_bike_availability())

    @patch("services.citibike_service.requests.get")
    def test_returns_none_on_request_error(self, mock_get):
        mock_get.side_effect = RuntimeError("network down")

        self.assertIsNone(self.service.get_bike_availability())


class ShouldNotifyTests(unittest.TestCase):
    def setUp(self):
        self.service = CitibikeService()

    def _avail(self, classic, ebikes):
        return BikeAvailability(
            classic_bikes=classic,
            ebikes=ebikes,
            station_id="test-station-uuid",
            station_name="Test Station",
        )

    def test_notifies_on_first_observation(self):
        self.assertTrue(self.service._should_notify(self._avail(5, 5)))

    def test_does_not_notify_when_unchanged(self):
        self.service._current_availability = self._avail(5, 5)
        self.assertFalse(self.service._should_notify(self._avail(5, 5)))

    def test_notifies_when_counts_change(self):
        self.service._current_availability = self._avail(5, 5)
        self.assertTrue(self.service._should_notify(self._avail(6, 5)))
        self.assertTrue(self.service._should_notify(self._avail(5, 4)))


if __name__ == "__main__":
    unittest.main()
