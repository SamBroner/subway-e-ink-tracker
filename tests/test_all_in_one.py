from datetime import datetime

from PIL import Image, ImageChops, ImageDraw

from config.config import config
from data.models import AppData
from services.weather_service import WeatherService
from tests.golden import fixtures as fx
from ui.fonts import fonts
from ui.panes.all_in_one import AllInOnePane
from ui.panes.base import PaneSurface, RenderContext


def _pane() -> AllInOnePane:
    return AllInOnePane((0, 0, config.display.WIDTH, config.display.HEIGHT))


def test_forecast_stations_preserve_rain_probability_and_icon_code():
    weather = fx.make_weather(
        current_code=fx.CODE_HEAVY_RAIN,
        current_precip=91,
        hourly_code=fx.CODE_HEAVY_RAIN,
        hourly_precip=78,
        hourly_rain_mm=2.0,
    )

    stations = _pane()._forecast_stations(weather, fx.FIXED_NOW)

    assert stations[0].precipitation == 91
    assert stations[1].precipitation == 78
    assert stations[1].report["chance_of_rain"] == 78
    assert stations[1].report["chance_of_snow"] == 0
    assert stations[1].report["condition"]["text"] == "Heavy rain"


def test_forecast_stations_preserve_snow_probability_and_icon_code():
    weather = fx.make_weather(
        current_code=fx.CODE_HEAVY_SNOW,
        current_precip=84,
        hourly_code=fx.CODE_HEAVY_SNOW,
        hourly_precip=73,
        hourly_snow_cm=1.5,
    )

    stations = _pane()._forecast_stations(weather, fx.FIXED_NOW)

    assert stations[0].precipitation == 84
    assert stations[1].precipitation == 73
    assert stations[1].report["chance_of_rain"] == 0
    assert stations[1].report["chance_of_snow"] == 73
    assert stations[1].report["condition"]["text"] == "Heavy snow"


def test_solar_events_drive_day_twilight_and_night_weights():
    weather = fx.make_weather()
    pane = _pane()
    stations = pane._forecast_stations(weather, fx.FIXED_NOW)
    events = pane._solar_events(weather, fx.FIXED_NOW)

    assert [(event.kind, event.when.strftime("%H:%M")) for event in events] == [
        ("sunset", "16:52")
    ]
    assert pane._ribbon_width(datetime(2026, 1, 15, 15, 0), stations, events, weather) == 24
    assert pane._ribbon_width(datetime(2026, 1, 15, 16, 40), stations, events, weather) == 24
    assert pane._ribbon_width(datetime(2026, 1, 15, 17, 0), stations, events, weather) == 12
    assert pane._ribbon_width(datetime(2026, 1, 15, 18, 0), stations, events, weather) == 4

    morning = datetime(2026, 1, 15, 6, 0)
    morning_weather = fx.make_weather(now=morning)
    morning_stations = pane._forecast_stations(morning_weather, morning)
    morning_events = pane._solar_events(morning_weather, morning)
    assert [(event.kind, event.when.strftime("%H:%M")) for event in morning_events] == [
        ("sunrise", "07:16")
    ]
    assert pane._ribbon_width(
        datetime(2026, 1, 15, 7, 0), morning_stations, morning_events, morning_weather
    ) == 12
    assert pane._ribbon_width(
        datetime(2026, 1, 15, 7, 20), morning_stations, morning_events, morning_weather
    ) == 24


def test_bird_layer_preserves_complete_collage_and_rises_into_arch():
    pane = _pane()
    birds = fx.make_birds()
    weather = fx.make_weather(
        current_code=fx.CODE_HEAVY_RAIN,
        current_precip=91,
        hourly_code=fx.CODE_HEAVY_RAIN,
        hourly_precip=78,
        hourly_rain_mm=2.0,
    )
    stations = pane._forecast_stations(weather, fx.FIXED_NOW)
    events = pane._solar_events(weather, fx.FIXED_NOW)
    exclusions = pane._forecast_exclusion_mask(stations, events, fx.FIXED_NOW)
    frame = Image.new("L", (pane.w, pane.h), 255)
    surface = PaneSurface(frame, (0, 0))
    context = RenderContext(data=AppData(birds=birds), now=fx.FIXED_NOW)

    pane._draw_birds(surface, context, exclusions)

    source = pane._bird_pane.collage_image(birds, exclusions)
    rendered = frame.crop((0, pane.BIRD_Y, pane.w, pane.BIRD_Y + pane.BIRD_HEIGHT))
    assert ImageChops.difference(rendered, source).getbbox() is None

    top_ink = ImageChops.invert(rendered.crop((0, 0, pane.w, 50)))
    assert top_ink.getbbox() is not None
    assert len(pane._bird_pane._last_placements) == len(birds.observations[:15])

    for placement in pane._bird_pane._last_placements:
        assert placement.bird_mask is not None
        bird_x, bird_y = placement.bird_origin
        region = exclusions.crop(
            (
                bird_x,
                bird_y,
                bird_x + placement.bird_mask.width,
                bird_y + placement.bird_mask.height,
            )
        )
        assert ImageChops.multiply(region, placement.bird_mask).getbbox() is None

    for index in (1, len(stations) - 1):
        x, y = pane._arc_point(pane.ARC_STATION_T[index])
        _time_xy, _temp_xy, precip_xy = pane._station_label_positions(
            index,
            len(stations),
            x,
            y,
        )
        assert exclusions.getpixel(
            (round(precip_xy[0]), round(precip_xy[1] - pane.BIRD_Y))
        ) == 255

    ribbon_x, ribbon_y = pane._arc_point(0.1)
    assert exclusions.getpixel(
        (round(ribbon_x), round(ribbon_y - pane.BIRD_Y))
    ) == 255
    assert exclusions.getpixel(
        (pane.w // 2, pane.BOTTOM_RAIL_TOP - pane.BIRD_Y)
    ) == 255


def test_monumental_bottom_rail_keeps_double_digit_counts_in_their_lanes():
    pane = _pane()
    draw = ImageDraw.Draw(Image.new("L", (pane.w, pane.h), 255))

    f_pair = draw.textbbox(
        (202, 1171),
        "16",
        font=pane._bottom_pair_font,
        anchor="mm",
    )
    g_pair = draw.textbbox(
        (446, 1171),
        "24",
        font=pane._bottom_pair_font,
        anchor="mm",
    )
    classic = draw.textbbox(
        (635, pane.BOTTOM_Y),
        "12",
        font=fonts.get("header"),
        anchor="mm",
    )
    electric = draw.textbbox(
        (787, pane.BOTTOM_Y),
        "17",
        font=fonts.get("header"),
        anchor="mm",
    )

    assert f_pair[2] < 280 - 48
    assert g_pair[2] < 500
    assert classic[0] >= 600
    assert classic[2] < 672
    assert electric[0] >= 752
    assert electric[2] <= pane.w


def test_solar_time_is_positioned_inside_the_arch():
    pane = _pane()
    x, y = pane._arc_point(0.25)
    label_x, label_y = pane._solar_event_label_position(0.25, x, y)

    assert label_x > x
    assert label_y > y


def test_weather_service_keeps_solar_times_in_forecast_days():
    service = WeatherService()
    data = {
        "daily": {
            "time": ["2026-01-15"],
            "weathercode": [2],
            "temperature_2m_max": [42],
            "temperature_2m_min": [30],
            "precipitation_probability_max": [10],
            "sunrise": ["2026-01-15T07:16"],
            "sunset": ["2026-01-15T16:52"],
        },
        "hourly": {
            "time": [f"2026-01-15T{hour:02d}:00" for hour in range(24)],
            "temperature_2m": [38] * 24,
            "precipitation_probability": [0] * 24,
            "rain": [0] * 24,
            "snowfall": [0] * 24,
            "weathercode": [2] * 24,
            "windspeed_10m": [6] * 24,
            "is_day": [1] * 24,
        },
    }

    days = service._get_forecast_days(data)

    assert days[0]["astro"] == {
        "sunrise": "2026-01-15T07:16",
        "sunset": "2026-01-15T16:52",
    }
