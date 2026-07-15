from datetime import datetime
from unittest.mock import Mock, patch

from config.config import config
from services.citibike_service import BikeAvailability
from ui.panes.citibike import CitibikePane
from ui.panes.weather_overview import WeatherOverviewPane


def _drawn_text(surface: Mock) -> list[str]:
    return [call.args[1] for call in surface.text.call_args_list]


def test_citibike_pane_labels_stale_counts_as_offline():
    pane = CitibikePane((0, 0, config.display.BOTTOM_VERTICAL_OFFSET, config.display.BOTTOM_SECTION_HEIGHT))
    surface = Mock()
    stale = BikeAvailability(
        classic_bikes=7,
        ebikes=4,
        station_id="station",
        station_name="Station",
        source_unavailable=True,
    )

    with patch("ui.panes.citibike.utils.get_ui_icon", return_value=Mock()):
        pane._draw_bike_panel(surface, stale)

    assert "BIKES OFFLINE" in _drawn_text(surface)


def test_weather_pane_labels_stale_forecast_as_offline():
    pane = WeatherOverviewPane(
        (
            config.display.BOTTOM_VERTICAL_OFFSET,
            config.display.WEATHER_SECTION_Y,
            config.display.WIDTH - config.display.BOTTOM_VERTICAL_OFFSET,
            config.display.BOTTOM_SECTION_HEIGHT,
        )
    )
    pane._draw_current_weather_large = Mock()
    surface = Mock()
    stale = {
        "source_unavailable": True,
        "current": {},
        "forecast": {"forecastday": []},
        "hourly": {},
    }

    pane._draw_weather_overview(surface, stale, datetime(2026, 7, 14, 12, 0))

    assert "WEATHER OFFLINE" in _drawn_text(surface)
