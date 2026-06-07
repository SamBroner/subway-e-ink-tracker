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
    }
    for key in file_values:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("DEBUG", "true")
    monkeypatch.setenv("STATION_ID", "shell-station")

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
