# Golden view tests

Pixel-for-pixel regression tests for the display renderer. Each scenario in
`scenarios.py` is rendered through the real layout engine (`ui.layout.getImage`)
at a fixed reference time and compared against a committed PNG in
`golden_views/`. These are the safety net for the pane-migration refactor:
every refactor step that is meant to be visually identical must leave all
goldens passing.

## How determinism works

Rendering is a **pure function of `(weather_data, trains, bikes, now)`**.
`getImage(..., now=FIXED_NOW)` is passed a fixed instant, so there is no
dependence on the wall clock or on any global service state. No `freezegun`,
no monkeypatching. Fixtures (`fixtures.py`) build weather/train/bike data by
hand in the shape `WeatherService` produces.

## Running

```sh
# Regression gate (default): compare against committed goldens.
.venv/bin/python -m pytest tests/golden/test_golden_views.py

# Regenerate goldens after an INTENTIONAL visual change, then eyeball + commit.
GOLDEN_UPDATE=1 .venv/bin/python -m pytest tests/golden/test_golden_views.py
# or as a plain script:
.venv/bin/python -m tests.golden.test_golden_views
```

On mismatch the rendered image is written as `golden_views/<name>.actual.png`
(git-ignored) so you can compare it against the committed `<name>.png`.

## Scenarios

Trains (F/G), weather, and bikes are varied independently plus one combined
stressor: `full_typical`, `no_trains`, `no_trains_minutes`, `no_trains_hours`,
`no_trains_far`, `service_down`, `no_f_only_g`, `no_g_only_f`, `many_f`,
`many_g`, `one_each`, `high_wind`, `high_rain`, `snow`, `thunderstorm`, `fog`,
`night`, `extreme_heat`, `extreme_cold`, `degraded_empty_hourly`, `zero_bikes`,
`many_bikes`, `null_bikes`, `combined_stress`.

Three subway states are distinguished: trains in the window render normally;
no trains in the window keeps the F & G logos and adds a status line at the
bottom of the pane reporting the gap until the next train (`no_trains*`); and
unreachable feeds show "Service unavailable" (`service_down`, driven by the
optional 5th scenario element `{"subway_unavailable": True}` forwarded to
`getImage`).

## Known issues (surfaced by these tests, deferred to the pane migration)

These goldens intentionally capture *current* (imperfect) behavior so the
baseline is truthful. They are expected to flip when the pane migration
reworks the weather-overview layout.

- **3-digit temps clip in the weather-overview pane.** In `extreme_heat`, the
  bottom-right "High 108°" runs off the right edge (the `°` is cut). The big
  current temp and the hourly lane handle 3-digit values fine; only the
  High/Low value column in `LayoutManager._draw_current_weather_large`
  overflows. To be fixed during Phase 2.
- **Missing `current` key crashes.** `degraded_empty_hourly` shows the renderer
  tolerates an **empty** `hourly` block (the hourly lane just goes blank).
  However, a payload *missing* the `current` key entirely still raises, because
  `_draw_bottom_sections` does an unguarded `weather_data["current"]`. If the
  app should render a "weather unavailable" state, that needs a real fallback —
  there is intentionally no golden for it yet.
