"""The punched-ribbon all-in-one weather, birds, transit, and bikes screen."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
import math
from typing import Iterable

from PIL import Image, ImageChops, ImageDraw

from config.config import config
from services.subway_service import TrainArrival
from services.weather_service import build_next_hours_forecast
from ui.fonts import fonts
from ui.panes.base import Pane, PaneSurface, RenderContext
from ui.panes.bird_collage import BirdCollagePane
import utils


@dataclass(frozen=True)
class ForecastStation:
    when: datetime
    report: dict

    @property
    def temperature(self) -> int | None:
        value = self.report.get("temp_f")
        if value is None:
            return None
        try:
            return round(float(value))
        except (TypeError, ValueError):
            return None

    @property
    def precipitation(self) -> int:
        chances = [
            self.report.get("chance_of_rain"),
            self.report.get("chance_of_snow"),
            self.report.get("chance_of_precipitation"),
            self.report.get("precip_chance"),
        ]
        numeric = []
        for value in chances:
            if value is None:
                continue
            try:
                numeric.append(float(value))
            except (TypeError, ValueError):
                continue
        return int(round(max(numeric, default=0)))

    @property
    def is_day(self) -> bool:
        return bool(self.report.get("is_day", 1))


class AllInOnePane(Pane):
    """Render the forecast-origin punched ribbon around the bird collage."""

    ARC_START = (48.0, 334.0)
    ARC_CONTROL = (412.0, -168.0)
    ARC_END = (777.0, 334.0)
    ARC_STATION_T = (0.0, 0.16, 0.36, 0.56, 0.76, 0.96)
    FORECAST_HOURS = 10
    TWILIGHT_MINUTES = 30
    BIRD_Y = 160
    BIRD_HEIGHT = 925
    BOTTOM_Y = 1158

    def __init__(self, rect: tuple[int, int, int, int]):
        super().__init__(rect)
        self._bird_pane = BirdCollagePane((0, 0, self.w, self.BIRD_HEIGHT), named=False)
        self._ribbon_cache_key: tuple[int, ...] | None = None
        self._ribbon_cache_mask: Image.Image | None = None

    def paint(self, surface: PaneSurface, ctx: RenderContext) -> None:
        weather = ctx.data.weather or {}
        stations = self._forecast_stations(weather, ctx.now)
        events = self._solar_events(weather, ctx.now)

        self._draw_header(surface, weather, ctx.now)
        self._draw_birds(surface, ctx)
        self._draw_ribbon(surface, stations, events, weather, ctx.now)
        self._draw_stations(surface, stations)
        self._draw_solar_event_times(surface, events, ctx.now)
        self._draw_bottom_rail(surface, ctx)

    def _draw_header(self, surface: PaneSurface, weather: dict, now: datetime) -> None:
        current = weather.get("current", {})
        condition = str(current.get("condition", {}).get("text", "Weather unavailable")).upper()
        condition_lines = self._wrap_text(condition, fonts.get("small"), 270, surface)
        for index, line in enumerate(condition_lines[:2]):
            surface.text((24, 20 + index * 23), line, font=fonts.get("small"), fill=0)

        forecast_days = weather.get("forecast", {}).get("forecastday", [])
        today = forecast_days[0].get("day", {}) if forecast_days else {}
        high = self._temperature_text(today.get("maxtemp_f"))
        low = self._temperature_text(today.get("mintemp_f"))
        detail_y = 65 if len(condition_lines) == 1 else 82
        surface.text((24, detail_y), "TODAY", font=fonts.get("small"), fill=0)
        surface.text((24, detail_y + 30), f"H{high} · L{low}", font=fonts.get("medium"), fill=0)

        surface.text(
            (801, 20),
            now.strftime("%a, %b %-d").upper(),
            font=fonts.get("small"),
            fill=0,
            anchor="ra",
        )
        time_text = now.strftime("%-I:%M")
        seconds_text = now.strftime(":%S %p").lower()
        surface.text((750, 36), time_text, font=fonts.get("header"), fill=0, anchor="ra")
        surface.text((754, 80), seconds_text, font=fonts.get("small"), fill=0, anchor="ls")

    def _draw_birds(self, surface: PaneSurface, ctx: RenderContext) -> None:
        collage = self._bird_pane.collage_image(ctx.data.birds)
        bird_ink = ImageChops.invert(collage)
        black = Image.new("L", collage.size, 0)
        surface.paste(black, (0, self.BIRD_Y), bird_ink)

    def _draw_ribbon(
        self,
        surface: PaneSurface,
        stations: list[ForecastStation],
        events: list[datetime],
        weather: dict,
        now: datetime,
    ) -> None:
        steps = 96
        end = now + timedelta(hours=self.FORECAST_HOURS)
        widths = []
        for index in range(steps):
            start_t = index / steps
            end_t = (index + 1) / steps
            midpoint = start_t + (end_t - start_t) / 2
            moment = now + (end - now) * midpoint
            widths.append(self._ribbon_width(moment, stations, events, weather))

        cache_key = tuple(widths)
        if self._ribbon_cache_mask is None or cache_key != self._ribbon_cache_key:
            scale = 3
            mask = Image.new("L", (self.w * scale, self.h * scale), 0)
            draw = ImageDraw.Draw(mask)
            run_start = 0
            for index in range(1, steps + 1):
                if index < steps and widths[index] == widths[run_start]:
                    continue
                points = [
                    tuple(int(round(value * scale)) for value in self._arc_point(point / steps))
                    for point in range(run_start, index + 1)
                ]
                draw.line(points, fill=255, width=widths[run_start] * scale, joint="curve")
                run_start = index
            self._ribbon_cache_mask = mask.resize((self.w, self.h), Image.Resampling.LANCZOS)
            self._ribbon_cache_key = cache_key

        surface.paste(Image.new("L", (self.w, self.h), 0), (0, 0), self._ribbon_cache_mask)

    def _draw_stations(self, surface: PaneSurface, stations: list[ForecastStation]) -> None:
        for index, (station, t) in enumerate(zip(stations, self.ARC_STATION_T)):
            x, y = self._arc_point(t)
            surface.ellipse((x - 29, y - 29, x + 29, y + 29), fill=255)
            try:
                icon = utils.getWeatherIcon(station.report, 44)
                surface.paste(icon, (int(x - 22), int(y - 22)), icon)
            except (FileNotFoundError, KeyError, OSError):
                surface.ellipse((x - 8, y - 8, x + 8, y + 8), outline=0, width=2)

            time_y = y - 39
            temp_y = y + 48
            precip_y = y + 70
            if index == len(stations) - 1:
                time_y = y - 52
                temp_y = y + 43
                precip_y = y + 65

            self._draw_backed_text(
                surface,
                (x, time_y),
                station.when.strftime("%-I%p").lower(),
                fonts.get("small"),
            )
            self._draw_backed_text(
                surface,
                (x, temp_y),
                self._temperature_text(station.temperature),
                fonts.get("medium"),
            )
            if station.precipitation > 0:
                self._draw_backed_text(
                    surface,
                    (x, precip_y),
                    f"{station.precipitation}%",
                    fonts.get("small"),
                )

    def _draw_solar_event_times(
        self,
        surface: PaneSurface,
        events: list[datetime],
        now: datetime,
    ) -> None:
        total_seconds = self.FORECAST_HOURS * 3600
        for event in events:
            t = (event - self._local_naive(now)).total_seconds() / total_seconds
            if not 0 < t < 1:
                continue
            x, y = self._arc_point(t)
            surface.line((x, y - 13, x, y + 13), fill=0, width=2)
            surface.text(
                (x, y - 23),
                event.strftime("%-I:%M"),
                font=fonts.get("small"),
                fill=0,
                anchor="ms",
            )

    def _draw_bottom_rail(self, surface: PaneSurface, ctx: RenderContext) -> None:
        trains = ctx.data.subway.trains if ctx.data.subway else []
        unavailable = ctx.data.subway.unavailable_lines if ctx.data.subway else frozenset()
        self._draw_route(
            surface,
            34,
            config.TRAIN_LINE_1,
            self._route_minutes(trains, config.TRAIN_LINE_1, ctx.now),
            config.TRAIN_LINE_1 in unavailable,
        )
        self._draw_route(
            surface,
            244,
            config.TRAIN_LINE_2,
            self._route_minutes(trains, config.TRAIN_LINE_2, ctx.now),
            config.TRAIN_LINE_2 in unavailable,
        )

        bike_icon = utils.get_ui_icon("bike", 54)
        surface.paste(bike_icon, (466, self.BOTTOM_Y - 27), bike_icon)
        classic = getattr(ctx.data.bikes, "classic_bikes", None)
        surface.text(
            (556, self.BOTTOM_Y),
            "--" if classic is None else str(classic),
            font=fonts.get("xlarge"),
            fill=0,
            anchor="mm",
        )

        ebike_icon = utils.get_ui_icon("lightningbolt", 46)
        surface.paste(ebike_icon, (637, self.BOTTOM_Y - 23), ebike_icon)
        electric = getattr(ctx.data.bikes, "ebikes", None)
        surface.text(
            (738, self.BOTTOM_Y),
            "--" if electric is None else str(electric),
            font=fonts.get("xlarge"),
            fill=0,
            anchor="mm",
        )

    def _draw_route(
        self,
        surface: PaneSurface,
        circle_x: int,
        route: str,
        minutes: list[int],
        unavailable: bool,
    ) -> None:
        radius = 27
        surface.ellipse((circle_x - radius, self.BOTTOM_Y - radius, circle_x + radius, self.BOTTOM_Y + radius), fill=0)
        surface.text((circle_x, self.BOTTOM_Y), route, font=fonts.get("xxlarge"), fill=255, anchor="mm")
        values: Iterable[str | int] = ("—",) if unavailable or not minutes else minutes[:3]
        for index, value in enumerate(values):
            surface.text(
                (80 + (circle_x - 34) + index * 48, self.BOTTOM_Y),
                str(value),
                font=fonts.get("large"),
                fill=0,
                anchor="mm",
            )

    def _forecast_stations(self, weather: dict, now: datetime) -> list[ForecastStation]:
        hourly = build_next_hours_forecast(weather, now, self.FORECAST_HOURS + 1)
        current = dict(weather.get("current", {}))
        if not current and hourly:
            current = dict(hourly[0])

        stations = [ForecastStation(when=now.replace(minute=0, second=0, microsecond=0), report=current)]
        for offset in range(2, self.FORECAST_HOURS + 1, 2):
            if offset < len(hourly):
                report = hourly[offset]
                when = self._parse_datetime(report.get("time")) or (now + timedelta(hours=offset))
                stations.append(ForecastStation(when=when, report=report))

        while len(stations) < len(self.ARC_STATION_T):
            offset = len(stations) * 2
            fallback = dict(stations[-1].report if stations else current)
            stations.append(ForecastStation(when=now + timedelta(hours=offset), report=fallback))
        return stations[:len(self.ARC_STATION_T)]

    def _solar_events(self, weather: dict, now: datetime) -> list[datetime]:
        start = self._local_naive(now)
        end = start + timedelta(hours=self.FORECAST_HOURS)
        events = []
        for forecast_day in weather.get("forecast", {}).get("forecastday", []):
            astro = forecast_day.get("astro", {})
            for key in ("sunrise", "sunset"):
                event = self._parse_datetime(astro.get(key))
                if event is not None and start < event < end:
                    events.append(event)
        return sorted(set(events))

    def _ribbon_width(
        self,
        moment: datetime,
        stations: list[ForecastStation],
        events: list[datetime],
        weather: dict,
    ) -> int:
        local_moment = self._local_naive(moment)
        if any(abs((event - local_moment).total_seconds()) <= self.TWILIGHT_MINUTES * 60 for event in events):
            return 12
        return 24 if self._is_day(local_moment, stations, weather) else 4

    def _is_day(self, moment: datetime, stations: list[ForecastStation], weather: dict) -> bool:
        for forecast_day in weather.get("forecast", {}).get("forecastday", []):
            astro = forecast_day.get("astro", {})
            sunrise = self._parse_datetime(astro.get("sunrise"))
            sunset = self._parse_datetime(astro.get("sunset"))
            if sunrise is not None and sunset is not None and sunrise.date() == moment.date():
                return sunrise <= moment < sunset
        nearest = min(
            stations,
            key=lambda station: abs((self._local_naive(station.when) - moment).total_seconds()),
            default=None,
        )
        return nearest.is_day if nearest is not None else True

    def _route_minutes(self, trains: list[TrainArrival], route: str, now: datetime) -> list[int]:
        minutes = []
        for train in trains:
            if train.route_id != route:
                continue
            if getattr(train, "arrival_timestamp", None):
                value = max(0, math.floor((train.arrival_timestamp - now.timestamp()) / 60))
            else:
                value = train.minutes_until_arrival
            if 1 <= value <= self.subway.MAX_TRAIN_MINUTES:
                minutes.append(value)
        return sorted(minutes)[:3]

    @classmethod
    def _arc_point(cls, t: float) -> tuple[float, float]:
        inverse = 1 - t
        return (
            inverse * inverse * cls.ARC_START[0]
            + 2 * inverse * t * cls.ARC_CONTROL[0]
            + t * t * cls.ARC_END[0],
            inverse * inverse * cls.ARC_START[1]
            + 2 * inverse * t * cls.ARC_CONTROL[1]
            + t * t * cls.ARC_END[1],
        )

    @staticmethod
    def _temperature_text(value) -> str:
        if value is None:
            return "--°"
        return f"{round(float(value))}°"

    @staticmethod
    def _parse_datetime(value) -> datetime | None:
        if not value:
            return None
        try:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except (TypeError, ValueError):
            return None
        return parsed.replace(tzinfo=None)

    @staticmethod
    def _local_naive(value: datetime) -> datetime:
        return value.replace(tzinfo=None)

    @staticmethod
    def _wrap_text(text: str, font, max_width: int, surface: PaneSurface) -> list[str]:
        words = text.split()
        if not words:
            return [""]
        lines = []
        current = words[0]
        for word in words[1:]:
            candidate = f"{current} {word}"
            if surface.textlength(candidate, font=font) <= max_width:
                current = candidate
            else:
                lines.append(current)
                current = word
        lines.append(current)
        return lines

    @staticmethod
    def _draw_backed_text(surface: PaneSurface, xy: tuple[float, float], text: str, font) -> None:
        bbox = surface.textbbox(xy, text, font=font, anchor="ms")
        padding = 2
        width = max(1, int(math.ceil(bbox[2] - bbox[0] + padding * 2)))
        height = max(1, int(math.ceil(bbox[3] - bbox[1] + padding * 2)))
        surface.paste(
            Image.new("L", (width, height), 255),
            (int(math.floor(bbox[0] - padding)), int(math.floor(bbox[1] - padding))),
        )
        surface.text(xy, text, font=font, fill=0, anchor="ms")
