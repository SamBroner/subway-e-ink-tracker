"""Named golden-view scenarios.

Each scenario is a (name, weather, trains, bikes) tuple built from the
deterministic fixtures. Names double as the golden PNG filenames.
"""

from typing import List

from tests.golden import fixtures as fx

# (name, weather, trains, bikes[, render_kwargs]) — the optional 5th element is
# a dict of extra kwargs forwarded to getImage (e.g. {"subway_unavailable": True}).
Scenario = tuple


def all_scenarios() -> List[Scenario]:
    typical_weather = fx.make_weather(current_code=fx.CODE_PARTLY)
    bikes = fx.make_bikes(8, 3)

    return [
        # --- typical baseline -------------------------------------------------
        ("full_typical", typical_weather, fx.make_trains([3, 9, 16], [5, 12, 24]), bikes),

        # --- train edge cases -------------------------------------------------
        # Nothing upcoming at all -> indefinite "not currently running".
        ("no_trains", typical_weather, fx.make_trains([], []), bikes),
        # Next trains exist but are beyond the display window (>40 min): the
        # message reports the gap. <100 min -> minutes; >=100 min -> hours;
        # >4 h -> the same "not currently running" text via the >240 branch.
        ("no_trains_minutes", typical_weather, fx.make_trains([55], [70]), bikes),
        ("no_trains_hours", typical_weather, fx.make_trains([130], []), bikes),
        ("no_trains_far", typical_weather, fx.make_trains([300], []), bikes),
        ("service_down", typical_weather, fx.make_trains([], []), bikes,
         {"subway_unavailable": True}),
        ("no_f_only_g", typical_weather, fx.make_trains([], [4, 11, 19, 26]), bikes),
        ("no_g_only_f", typical_weather, fx.make_trains([2, 7, 13, 20], []), bikes),
        ("many_f", typical_weather, fx.make_trains([2, 5, 9, 13, 18, 25, 33], [6]), bikes),
        ("many_g", typical_weather, fx.make_trains([8], [3, 7, 11, 15, 22, 30]), bikes),
        ("one_each", typical_weather, fx.make_trains([6], [9]), bikes),

        # --- weather edge cases ----------------------------------------------
        ("high_wind",
         fx.make_weather(current_code=fx.CODE_OVERCAST, current_wind=28, hourly_wind=24),
         fx.make_trains([4, 10], [7, 15]), bikes),
        ("high_rain",
         fx.make_weather(current_code=fx.CODE_HEAVY_RAIN, current_precip=95, current_wind=14,
                         hourly_code=fx.CODE_HEAVY_RAIN, hourly_precip=80, hourly_rain_mm=2.0,
                         daily_precip=90, current_temp=44, daily_high=47, daily_low=40),
         fx.make_trains([4, 10], [7, 15]), bikes),
        ("snow",
         fx.make_weather(current_code=fx.CODE_HEAVY_SNOW, current_precip=80, current_temp=28,
                         hourly_code=fx.CODE_HEAVY_SNOW, hourly_precip=75, hourly_snow_cm=1.5,
                         hourly_temp=27, daily_high=31, daily_low=22, daily_precip=80),
         fx.make_trains([4, 10], [7, 15]), bikes),
        ("thunderstorm",
         fx.make_weather(current_code=fx.CODE_THUNDERSTORM, current_precip=70, current_wind=18,
                         hourly_code=fx.CODE_THUNDERSTORM, hourly_precip=65, hourly_rain_mm=3.0,
                         daily_precip=75, current_temp=58, daily_high=62, daily_low=50),
         fx.make_trains([4, 10], [7, 15]), bikes),
        ("fog",
         fx.make_weather(current_code=fx.CODE_FOG, hourly_code=fx.CODE_FOG),
         fx.make_trains([4, 10], [7, 15]), bikes),
        ("night",
         fx.make_weather(current_code=fx.CODE_PARTLY, is_day=0),
         fx.make_trains([4, 10], [7, 15]), bikes),
        ("extreme_heat",
         fx.make_weather(current_code=fx.CODE_CLEAR, current_temp=103, current_wind=5,
                         hourly_code=fx.CODE_CLEAR, hourly_temp=101,
                         daily_high=108, daily_low=88, daily_precip=0),
         fx.make_trains([4, 10], [7, 15]), bikes),
        ("extreme_cold",
         fx.make_weather(current_code=fx.CODE_LIGHT_SNOW, current_temp=-5, current_precip=40,
                         current_wind=22, hourly_code=fx.CODE_LIGHT_SNOW, hourly_temp=-6,
                         hourly_precip=35, hourly_snow_cm=0.4,
                         daily_high=8, daily_low=-12, daily_precip=40),
         fx.make_trains([4, 10], [7, 15]), bikes),
        ("degraded_empty_hourly",
         fx.make_weather(empty_hourly=True),
         fx.make_trains([4, 10], [7, 15]), bikes),

        # --- bike edge cases --------------------------------------------------
        ("zero_bikes", typical_weather, fx.make_trains([4, 10], [7, 15]), fx.make_bikes(0, 0)),
        ("many_bikes", typical_weather, fx.make_trains([4, 10], [7, 15]), fx.make_bikes(99, 45)),
        ("null_bikes", typical_weather, fx.make_trains([4, 10], [7, 15]), None),

        # --- combined stressor ------------------------------------------------
        ("combined_stress",
         fx.make_weather(current_code=fx.CODE_HEAVY_RAIN, current_precip=92, current_wind=30,
                         hourly_code=fx.CODE_HEAVY_RAIN, hourly_precip=85, hourly_rain_mm=2.5,
                         daily_precip=95, current_temp=49, daily_high=53, daily_low=44),
         fx.make_trains([2, 5, 9, 13, 18, 25], [3, 7, 11, 22]), fx.make_bikes(99, 45)),
    ]
