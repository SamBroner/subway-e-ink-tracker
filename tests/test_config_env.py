import importlib.util
import os
import sys
from pathlib import Path


def test_shell_environment_takes_precedence_over_dotenv(monkeypatch):
    file_values = {
        "DEBUG": "false",
        "STATION_ID": "file-station",
        "TRAIN_LINE_1": "F",
        "TRAIN_LINE_2": "G",
        "CITIBIKE_STATION_ID": "file-bike-station",
        "CITIBIKE_STATION_NAME": "File Bike Station",
        "BIRD_RESULT_LIMIT": "11",
    }
    for key in file_values:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("DEBUG", "true")
    monkeypatch.setenv("STATION_ID", "shell-station")
    monkeypatch.setenv("BIRD_RESULT_LIMIT", "19")

    calls = []

    def fake_load_dotenv(path, override=False):
        calls.append({"path": Path(path), "override": override})
        for key, value in file_values.items():
            if override or os.getenv(key) is None:
                monkeypatch.setenv(key, value)
        return True

    monkeypatch.setattr("dotenv.load_dotenv", fake_load_dotenv)

    module_path = Path(__file__).resolve().parents[1] / "config" / "config.py"
    module_name = "_config_env_precedence_under_test"
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, module_name, module)
    assert spec.loader is not None
    spec.loader.exec_module(module)

    assert calls == [{
        "path": module_path.parent / ".env",
        "override": False,
    }]
    assert module.config.DEBUG is True
    assert module.config.STATION_ID == "shell-station"
    assert module.config.TRAIN_LINE_1 == "F"
    assert module.config.CITIBIKE_STATION_NAME == "File Bike Station"
    assert module.config.BIRD_RESULT_LIMIT == 19


def test_bird_result_limit_defaults_to_15(monkeypatch):
    file_values = {
        "DEBUG": "false",
        "STATION_ID": "file-station",
        "TRAIN_LINE_1": "F",
        "TRAIN_LINE_2": "G",
        "CITIBIKE_STATION_ID": "file-bike-station",
        "CITIBIKE_STATION_NAME": "File Bike Station",
    }
    for key in [*file_values.keys(), "BIRD_RESULT_LIMIT"]:
        monkeypatch.delenv(key, raising=False)

    def fake_load_dotenv(path, override=False):
        for key, value in file_values.items():
            if override or os.getenv(key) is None:
                monkeypatch.setenv(key, value)
        return True

    monkeypatch.setattr("dotenv.load_dotenv", fake_load_dotenv)

    module_path = Path(__file__).resolve().parents[1] / "config" / "config.py"
    module_name = "_config_bird_limit_default_under_test"
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, module_name, module)
    assert spec.loader is not None
    spec.loader.exec_module(module)

    assert module.config.BIRD_RESULT_LIMIT == 15


def test_touch_config_defaults(monkeypatch):
    file_values = {
        "DEBUG": "false",
        "STATION_ID": "file-station",
        "TRAIN_LINE_1": "F",
        "TRAIN_LINE_2": "G",
        "CITIBIKE_STATION_ID": "file-bike-station",
        "CITIBIKE_STATION_NAME": "File Bike Station",
    }
    for key in [*file_values.keys(), "TOUCH_ENABLED", "TOUCH_CHANNEL", "TOUCH_I2C_ADDRESS"]:
        monkeypatch.delenv(key, raising=False)

    def fake_load_dotenv(path, override=False):
        for key, value in file_values.items():
            if override or os.getenv(key) is None:
                monkeypatch.setenv(key, value)
        return True

    monkeypatch.setattr("dotenv.load_dotenv", fake_load_dotenv)

    module_path = Path(__file__).resolve().parents[1] / "config" / "config.py"
    module_name = "_config_touch_defaults_under_test"
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, module_name, module)
    assert spec.loader is not None
    spec.loader.exec_module(module)

    assert module.config.TOUCH_ENABLED is False
    assert module.config.TOUCH_CHANNEL == 0
    assert module.config.TOUCH_I2C_ADDRESS == 0x5A


def test_timing_config_uses_dotenv_and_shell_overrides(monkeypatch):
    file_values = {
        "DEBUG": "false",
        "STATION_ID": "file-station",
        "TRAIN_LINE_1": "F",
        "TRAIN_LINE_2": "G",
        "CITIBIKE_STATION_ID": "file-bike-station",
        "CITIBIKE_STATION_NAME": "File Bike Station",
        "WEATHER_UPDATE_SECONDS": "444",
        "DISPLAY_CLEAR_COOLDOWN_SECONDS": "8",
    }
    timing_keys = [
        "WEATHER_UPDATE_SECONDS",
        "SUBWAY_UPDATE_SECONDS",
        "CITIBIKE_UPDATE_SECONDS",
        "BIRD_UPDATE_SECONDS",
        "DISPLAY_MIN_INTERVAL_SECONDS",
        "DISPLAY_CLEAR_COOLDOWN_SECONDS",
    ]
    for key in [*file_values.keys(), *timing_keys]:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("SUBWAY_UPDATE_SECONDS", "7")
    monkeypatch.setenv("DISPLAY_CLEAR_COOLDOWN_SECONDS", "12")

    def fake_load_dotenv(path, override=False):
        for key, value in file_values.items():
            if override or os.getenv(key) is None:
                monkeypatch.setenv(key, value)
        return True

    monkeypatch.setattr("dotenv.load_dotenv", fake_load_dotenv)

    module_path = Path(__file__).resolve().parents[1] / "config" / "config.py"
    module_name = "_config_timing_overrides_under_test"
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, module_name, module)
    assert spec.loader is not None
    spec.loader.exec_module(module)

    assert module.config.timing.WEATHER_UPDATE_SECONDS == 444
    assert module.config.timing.SUBWAY_UPDATE_SECONDS == 7
    assert module.config.timing.CITIBIKE_UPDATE_SECONDS == 60
    assert module.config.timing.BIRD_UPDATE_SECONDS == 900
    assert module.config.timing.DISPLAY_CLEAR_COOLDOWN_SECONDS == 12
