"""The punched-ribbon all-in-one weather, birds, transit, and bikes screen."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
import math

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


@dataclass(frozen=True)
class SolarEvent:
    when: datetime
    kind: str


class AllInOnePane(Pane):
    """Render the forecast-origin punched ribbon around the bird collage."""

    ARC_START = (48.0, 364.0)
    ARC_CONTROL = (412.0, -138.0)
    ARC_END = (777.0, 364.0)
    ARC_STATION_T = (0.0, 0.16, 0.36, 0.56, 0.76, 0.96)
    FORECAST_HOURS = 10
    TWILIGHT_MINUTES = 30
    BIRD_Y = 160
    BIRD_HEIGHT = 925
    FORECAST_CLEARANCE = 5
    FORECAST_ICON_RADIUS = 34
    FORECAST_ICON_SIZE = 52
    TEXT_BACKING_PADDING = 2
    BOTTOM_Y = 1137
    BOTTOM_RAIL_TOP = 1070

    def __init__(self, rect: tuple[int, int, int, int]):
        super().__init__(rect)
        self._bird_pane = BirdCollagePane((0, 0, self.w, self.BIRD_HEIGHT), named=False)
        self._bottom_pair_font = fonts.get("xxlarge").font_variant(size=48)
        self._ribbon_cache_key: tuple[int, ...] | None = None
        self._ribbon_cache_mask: Image.Image | None = None

    def paint(self, surface: PaneSurface, ctx: RenderContext) -> None:
        weather = ctx.data.weather or {}
        stations = self._forecast_stations(weather, ctx.now)
        events = self._solar_events(weather, ctx.now)
        bird_exclusions = self._forecast_exclusion_mask(stations, events, ctx.now)

        self._draw_header(surface, weather, ctx.now)
        self._draw_birds(surface, ctx, bird_exclusions)
        self._draw_ribbon(surface, stations, events, weather, ctx.now)
        self._draw_stations(surface, stations)
        self._draw_solar_event_times(surface, events, ctx.now)
        self._draw_bottom_rail(surface, ctx)

    def _draw_header(self, surface: PaneSurface, weather: dict, now: datetime) -> None:
        current = weather.get("current", {})
        forecast_days = weather.get("forecast", {}).get("forecastday", [])
        today = forecast_days[0].get("day", {}) if forecast_days else {}
        high = self._temperature_text(today.get("maxtemp_f"))
        low = self._temperature_text(today.get("mintemp_f"))
        current_temp = self._temperature_text(current.get("temp_f"))

        icon = utils.getWeatherIcon(current, 136)
        alpha = icon.getchannel("A") if icon.mode == "RGBA" else icon
        visible = alpha.getbbox()
        if visible:
            visible_icon = icon.crop(visible)
            target_height = 112
            scale = min(136 / visible_icon.width, target_height / visible_icon.height)
            visible_icon = visible_icon.resize(
                (
                    max(1, round(visible_icon.width * scale)),
                    max(1, round(visible_icon.height * scale)),
                ),
                Image.Resampling.LANCZOS,
            )
            icon_y = 5 + (target_height - visible_icon.height) // 2
            surface.paste(visible_icon, (144, icon_y), visible_icon)

        numeric_current = current_temp.rstrip("°")
        digit_count = sum(character.isdigit() for character in numeric_current)
        current_center = 68 if digit_count >= 3 else 66
        current_size = 72 if digit_count >= 3 else 76
        current_font = fonts.get("xheader").font_variant(size=current_size)
        surface.text(
            (current_center, 45),
            numeric_current,
            font=current_font,
            fill=0,
            anchor="mm",
        )
        numeric_width = surface.textlength(numeric_current, font=current_font)
        degree_font = fonts.get("large").font_variant(
            size=max(24, round(current_size * 0.46))
        )
        surface.text(
            (current_center + numeric_width / 2 + 2, 22),
            "°",
            font=degree_font,
            fill=0,
            anchor="lm",
        )

        daily_text = f"{high}/{low}"
        daily_size = 27 if len(daily_text) >= 8 else 31
        daily_font = fonts.get("large").font_variant(size=daily_size)
        slash_width = surface.textlength("/", font=daily_font)
        high_width = surface.textlength(high, font=daily_font)
        low_width = surface.textlength(low, font=daily_font)
        gap = 1
        if digit_count == 1:
            slash_x = 66
        elif digit_count == 2:
            slash_x = current_center + 3
        else:
            total_width = high_width + gap + slash_width + gap + low_width
            range_left = current_center + 6 - total_width / 2
            slash_x = range_left + high_width + gap + slash_width / 2
        surface.text((slash_x, 109), "/", font=daily_font, fill=0, anchor="mm")
        surface.text(
            (slash_x - slash_width / 2 - gap, 109),
            high,
            font=daily_font,
            fill=0,
            anchor="rm",
        )
        surface.text(
            (slash_x + slash_width / 2 + gap, 109),
            low,
            font=daily_font,
            fill=0,
            anchor="lm",
        )

        minute_font = fonts.get("xheader").font_variant(size=64)
        seconds_font = fonts.get("large").font_variant(size=52)
        suffix_font = fonts.get("small").font_variant(size=20)
        suffix = now.strftime("%p")[0].lower()
        suffix_right = 796
        suffix_width = surface.textlength(suffix, font=suffix_font)
        seconds_text = now.strftime(":%S")
        seconds_width = surface.textlength(seconds_text, font=seconds_font)
        seconds_left = suffix_right - suffix_width - 7 - seconds_width
        surface.text(
            (seconds_left - 2, 47),
            now.strftime("%-I:%M"),
            font=minute_font,
            fill=0,
            anchor="rm",
        )
        surface.text(
            (seconds_left, 47),
            seconds_text,
            font=seconds_font,
            fill=0,
            anchor="lm",
        )
        surface.text(
            (suffix_right, 59),
            suffix,
            font=suffix_font,
            fill=0,
            anchor="rm",
        )
        surface.text(
            (suffix_right, 94),
            now.strftime("%a, %b %-d").upper(),
            font=fonts.get("medium"),
            fill=0,
            anchor="rt",
        )

    def _draw_birds(
        self,
        surface: PaneSurface,
        ctx: RenderContext,
        exclusion_mask: Image.Image | None = None,
    ) -> None:
        collage = self._bird_pane.collage_image(ctx.data.birds, exclusion_mask)
        bird_ink = ImageChops.invert(collage)
        black = Image.new("L", collage.size, 0)
        surface.paste(black, (0, self.BIRD_Y), bird_ink)

    def _forecast_exclusion_mask(
        self,
        stations: list[ForecastStation],
        events: list[SolarEvent],
        now: datetime,
    ) -> Image.Image:
        """Reserve the actual foreground geometry before packing the birds."""
        mask = Image.new("L", (self.w, self.BIRD_HEIGHT), 0)
        draw = ImageDraw.Draw(mask)

        def reserve_box(box: tuple[int, int, int, int]) -> None:
            clearance = self.FORECAST_CLEARANCE
            draw.rectangle(
                (
                    box[0] - clearance,
                    box[1] - self.BIRD_Y - clearance,
                    box[2] + clearance,
                    box[3] - self.BIRD_Y + clearance,
                ),
                fill=255,
            )

        arc_points = [
            (x, y - self.BIRD_Y)
            for x, y in (self._arc_point(step / 96) for step in range(97))
        ]
        draw.line(
            arc_points,
            fill=255,
            width=24 + self.FORECAST_CLEARANCE * 2,
            joint="curve",
        )
        draw.rectangle(
            (0, self.BOTTOM_RAIL_TOP - self.BIRD_Y, self.w, self.BIRD_HEIGHT),
            fill=255,
        )

        for index, (station, t) in enumerate(zip(stations, self.ARC_STATION_T)):
            x, y = self._arc_point(t)
            radius = self.FORECAST_ICON_RADIUS
            draw.ellipse(
                (x - radius, y - self.BIRD_Y - radius, x + radius, y - self.BIRD_Y + radius),
                fill=255,
            )

            time_xy, temp_xy, precip_xy = self._station_label_positions(
                index,
                len(stations),
                x,
                y,
            )
            labels = [
                (time_xy, station.when.strftime("%-I%p").lower(), fonts.get("small")),
                (temp_xy, self._temperature_text(station.temperature), fonts.get("large")),
            ]
            if station.precipitation > 0:
                labels.append((precip_xy, f"{station.precipitation}%", fonts.get("small")))
            for xy, text, font in labels:
                reserve_box(self._backed_text_box(xy, text, font))

        total_seconds = self.FORECAST_HOURS * 3600
        for event in events:
            t = (event.when - self._local_naive(now)).total_seconds() / total_seconds
            if not 0 < t < 1:
                continue
            x, y = self._arc_point(t)
            label_xy = self._solar_event_label_position(t, x, y)
            label = event.when.strftime("%-I:%M")
            reserve_box(self._backed_text_box(label_xy, label, fonts.get("small")))

        return mask

    def _draw_ribbon(
        self,
        surface: PaneSurface,
        stations: list[ForecastStation],
        events: list[SolarEvent],
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
            aperture = self.FORECAST_ICON_SIZE // 2 + 7
            surface.ellipse((x - aperture, y - aperture, x + aperture, y + aperture), fill=255)
            try:
                icon = utils.getWeatherIcon(station.report, self.FORECAST_ICON_SIZE)
                surface.paste(
                    icon,
                    (int(x - self.FORECAST_ICON_SIZE / 2), int(y - self.FORECAST_ICON_SIZE / 2)),
                    icon,
                )
            except (FileNotFoundError, KeyError, OSError):
                surface.ellipse((x - 8, y - 8, x + 8, y + 8), outline=0, width=2)

            time_xy, temp_xy, precip_xy = self._station_label_positions(
                index,
                len(stations),
                x,
                y,
            )

            self._draw_backed_text(
                surface,
                time_xy,
                station.when.strftime("%-I%p").lower(),
                fonts.get("small"),
            )
            self._draw_backed_text(
                surface,
                temp_xy,
                self._temperature_text(station.temperature),
                fonts.get("large"),
            )
            if station.precipitation > 0:
                self._draw_backed_text(
                    surface,
                    precip_xy,
                    f"{station.precipitation}%",
                    fonts.get("small"),
                )

    @staticmethod
    def _station_label_positions(
        index: int,
        station_count: int,
        x: float,
        y: float,
    ) -> tuple[tuple[float, float], tuple[float, float], tuple[float, float]]:
        if index == station_count - 1:
            return ((x, y - 48), (x, y + 50), (x, y + 67))

        time_x = x - 17 if index == 0 else x
        detail_x = x + 20 if index == 1 else x
        return ((time_x, y - 39), (detail_x, y + 55), (detail_x, y + 72))

    def _draw_solar_event_times(
        self,
        surface: PaneSurface,
        events: list[SolarEvent],
        now: datetime,
    ) -> None:
        total_seconds = self.FORECAST_HOURS * 3600
        for event in events:
            t = (event.when - self._local_naive(now)).total_seconds() / total_seconds
            if not 0 < t < 1:
                continue
            x, y = self._arc_point(t)
            label_xy = self._solar_event_label_position(t, x, y)

            surface.ellipse((x - 7, y - 7, x + 7, y + 7), fill=255)
            surface.ellipse((x - 4, y - 4, x + 4, y + 4), outline=0, width=2)
            self._draw_backed_text(
                surface,
                label_xy,
                event.when.strftime("%-I:%M"),
                font=fonts.get("small"),
            )

    def _draw_bottom_rail(self, surface: PaneSurface, ctx: RenderContext) -> None:
        trains = ctx.data.subway.trains if ctx.data.subway else []
        unavailable = ctx.data.subway.unavailable_lines if ctx.data.subway else frozenset()
        self._draw_route(
            surface,
            48,
            140,
            202,
            config.TRAIN_LINE_1,
            self._route_minutes(trains, config.TRAIN_LINE_1, ctx.now),
            config.TRAIN_LINE_1 in unavailable,
        )
        self._draw_route(
            surface,
            280,
            372,
            446,
            config.TRAIN_LINE_2,
            self._route_minutes(trains, config.TRAIN_LINE_2, ctx.now),
            config.TRAIN_LINE_2 in unavailable,
        )

        bike_icon = utils.get_ui_icon("bike", 100)
        surface.paste(bike_icon, (500, self.BOTTOM_Y - 50), bike_icon)
        classic = getattr(ctx.data.bikes, "classic_bikes", None)
        surface.text(
            (635, self.BOTTOM_Y),
            "--" if classic is None else str(classic),
            font=fonts.get("header"),
            fill=0,
            anchor="mm",
        )

        ebike_icon = utils.get_ui_icon("lightningbolt", 80)
        surface.paste(ebike_icon, (672, self.BOTTOM_Y - 40), ebike_icon)
        electric = getattr(ctx.data.bikes, "ebikes", None)
        surface.text(
            (787, self.BOTTOM_Y),
            "--" if electric is None else str(electric),
            font=fonts.get("header"),
            fill=0,
            anchor="mm",
        )

    def _draw_route(
        self,
        surface: PaneSurface,
        circle_x: int,
        lead_x: int,
        pair_x: int,
        route: str,
        minutes: list[int],
        unavailable: bool,
    ) -> None:
        radius = 48
        surface.ellipse(
            (
                circle_x - radius,
                self.BOTTOM_Y - radius,
                circle_x + radius,
                self.BOTTOM_Y + radius,
            ),
            fill=0,
        )
        surface.text(
            (circle_x, self.BOTTOM_Y),
            route,
            font=fonts.get("header"),
            fill=255,
            anchor="mm",
        )
        values = (
            ["—"]
            if unavailable or not minutes
            else [str(value) for value in minutes[:3]]
        )
        surface.text(
            (lead_x, self.BOTTOM_Y),
            values[0],
            font=fonts.get("xheader"),
            fill=0,
            anchor="mm",
        )
        for value, y in zip(values[1:], (1107, 1171)):
            surface.text(
                (pair_x, y),
                value,
                font=self._bottom_pair_font,
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

    def _solar_events(self, weather: dict, now: datetime) -> list[SolarEvent]:
        start = self._local_naive(now)
        end = start + timedelta(hours=self.FORECAST_HOURS)
        events = []
        for forecast_day in weather.get("forecast", {}).get("forecastday", []):
            astro = forecast_day.get("astro", {})
            for key in ("sunrise", "sunset"):
                event = self._parse_datetime(astro.get(key))
                if event is not None and start < event < end:
                    events.append(SolarEvent(when=event, kind=key))
        return sorted(set(events), key=lambda event: event.when)

    def _ribbon_width(
        self,
        moment: datetime,
        stations: list[ForecastStation],
        events: list[SolarEvent],
        weather: dict,
    ) -> int:
        local_moment = self._local_naive(moment)
        if self._is_day(local_moment, stations, weather):
            return 24
        if any(
            abs((event.when - local_moment).total_seconds()) <= self.TWILIGHT_MINUTES * 60
            for event in events
        ):
            return 12
        return 4

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

    @classmethod
    def _solar_event_label_position(
        cls,
        t: float,
        x: float,
        y: float,
    ) -> tuple[float, float]:
        inverse = 1 - t
        tangent_x = 2 * (
            inverse * (cls.ARC_CONTROL[0] - cls.ARC_START[0])
            + t * (cls.ARC_END[0] - cls.ARC_CONTROL[0])
        )
        tangent_y = 2 * (
            inverse * (cls.ARC_CONTROL[1] - cls.ARC_START[1])
            + t * (cls.ARC_END[1] - cls.ARC_CONTROL[1])
        )
        length = max(1.0, math.hypot(tangent_x, tangent_y))
        normal_x = -tangent_y / length
        normal_y = tangent_x / length
        distance = 52
        return (x + normal_x * distance, y + normal_y * distance)

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
    def _text_box(xy: tuple[float, float], text: str, font) -> tuple[int, int, int, int]:
        draw = ImageDraw.Draw(Image.new("L", (1, 1), 255))
        bbox = draw.textbbox(xy, text, font=font, anchor="ms")
        return (
            int(math.floor(bbox[0])),
            int(math.floor(bbox[1])),
            int(math.ceil(bbox[2])),
            int(math.ceil(bbox[3])),
        )

    @classmethod
    def _backed_text_box(cls, xy: tuple[float, float], text: str, font) -> tuple[int, int, int, int]:
        bbox = cls._text_box(xy, text, font)
        padding = cls.TEXT_BACKING_PADDING
        return (
            bbox[0] - padding,
            bbox[1] - padding,
            bbox[2] + padding,
            bbox[3] + padding,
        )

    @classmethod
    def _draw_backed_text(cls, surface: PaneSurface, xy: tuple[float, float], text: str, font) -> None:
        box = cls._backed_text_box(xy, text, font)
        width = max(1, box[2] - box[0])
        height = max(1, box[3] - box[1])
        surface.paste(
            Image.new("L", (width, height), 255),
            (box[0], box[1]),
        )
        surface.text(xy, text, font=font, fill=0, anchor="ms")
