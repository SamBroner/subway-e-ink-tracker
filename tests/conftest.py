"""Shared pytest defaults for modules that import runtime config at collection."""

import os


_CONFIG_DEFAULTS = {
    "STATION_ID": "F20S",
    "TRAIN_LINE_1": "F",
    "TRAIN_LINE_2": "G",
    "CITIBIKE_STATION_ID": "test-station",
    "CITIBIKE_STATION_NAME": "Test Station",
}


for key, value in _CONFIG_DEFAULTS.items():
    os.environ.setdefault(key, value)
