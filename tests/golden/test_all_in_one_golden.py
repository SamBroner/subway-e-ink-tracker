"""Pixel-exact golden coverage for the all-in-one screen's weather modes."""

import os
from pathlib import Path
import sys

import pytest
from PIL import Image, ImageChops

from data.models import AppData
from services.subway_service import SubwayResult
from tests.golden import fixtures as fx
from ui.layout import getImageFromAppData


GOLDEN_DIR = Path(__file__).parent / "golden_views"
REFERENCE_PLATFORM = "darwin"
RUN_PLATFORM_GOLDENS = os.environ.get("RUN_PLATFORM_GOLDENS") == "1"


SCENARIOS = [
    (
        "all_in_one_typical",
        fx.make_weather(current_code=fx.CODE_PARTLY, hourly_code=fx.CODE_PARTLY, hourly_precip=10),
    ),
    (
        "all_in_one_rain",
        fx.make_weather(
            current_code=fx.CODE_HEAVY_RAIN,
            current_precip=91,
            current_temp=44,
            hourly_code=fx.CODE_HEAVY_RAIN,
            hourly_precip=78,
            hourly_rain_mm=2.0,
            hourly_temp=43,
            daily_high=47,
            daily_low=40,
        ),
    ),
    (
        "all_in_one_snow",
        fx.make_weather(
            current_code=fx.CODE_HEAVY_SNOW,
            current_precip=84,
            current_temp=28,
            hourly_code=fx.CODE_HEAVY_SNOW,
            hourly_precip=73,
            hourly_snow_cm=1.5,
            hourly_temp=27,
            daily_high=31,
            daily_low=22,
        ),
    ),
]


def render(name: str, weather: dict) -> Image.Image:
    del name
    app_data = AppData(
        weather=weather,
        subway=SubwayResult(trains=fx.make_trains([3, 9, 16], [5, 12, 24])),
        bikes=fx.make_bikes(8, 3),
        birds=fx.make_birds(),
    )
    return getImageFromAppData(app_data, now=fx.FIXED_NOW, screen_name="all-in-one").rotate(180)


@pytest.mark.parametrize(("name", "weather"), SCENARIOS, ids=[row[0] for row in SCENARIOS])
def test_all_in_one_golden(name: str, weather: dict):
    if sys.platform != REFERENCE_PLATFORM and not RUN_PLATFORM_GOLDENS:
        pytest.skip("all-in-one goldens use the macOS reference renderer")

    rendered = render(name, weather)
    golden_path = GOLDEN_DIR / f"{name}.png"
    if os.environ.get("GOLDEN_UPDATE"):
        rendered.save(golden_path)
        pytest.skip(f"GOLDEN_UPDATE set; wrote {golden_path}")

    assert golden_path.exists(), f"Missing golden for {name}; regenerate with GOLDEN_UPDATE=1"
    golden = Image.open(golden_path).convert(rendered.mode)
    diff = ImageChops.difference(rendered, golden)
    assert diff.getbbox() is None
