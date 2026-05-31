"""Train section pane: F/G arrivals, no-trains notice, or service-unavailable."""

from datetime import datetime
from typing import List, Optional
import math

from PIL import ImageDraw

from config.config import config
from ui.fonts import fonts
from services.subway_service import TrainArrival
from ui.panes.base import Pane


class SubwayPane(Pane):
    """Train section: F/G arrivals, no-trains notice, or service-unavailable."""

    def render(self, img, draw, ctx):
        self._draw_subway_info(draw, ctx.trains, ctx.now, ctx.subway_unavailable)

    def _draw_subway_info(self, draw: ImageDraw.ImageDraw, trains: List[TrainArrival], now: datetime, subway_unavailable: bool = False):
        """Draw subway arrival information"""
        if subway_unavailable:
            self._draw_service_unavailable_message(draw)
            return

        next_f_trains, next_g_trains = self._select_display_trains(trains, now)
        if not next_f_trains and not next_g_trains:
            # Feeds are up but nothing is arriving within the display window.
            self._draw_no_trains(draw, trains, now)
            return

        # Draw next F and G trains
        self._draw_next_trains(draw, next_f_trains, next_g_trains, now)

    def _get_train_display_minutes(self, train: TrainArrival, now: datetime) -> int:
        """Get countdown minutes from absolute arrival time when available."""
        if getattr(train, "arrival_timestamp", None) is not None:
            return max(0, math.floor((train.arrival_timestamp - now.timestamp()) / 60))
        return train.minutes_until_arrival

    def _select_display_trains(self, trains: List[TrainArrival], now: datetime) -> tuple[List[TrainArrival], List[TrainArrival]]:
        """Pick the F and G trains to show: those arriving within the display window."""
        f_trains = [t for t in trains if t.route_id == config.TRAIN_LINE_1]
        g_trains = [t for t in trains if t.route_id == config.TRAIN_LINE_2]

        def filter_trains(train_list: List[TrainArrival], max_trains: int) -> List[TrainArrival]:
            windowed = [
                t for t in train_list
                if self.subway.MIN_TRAIN_MINUTES <= self._get_train_display_minutes(t, now) <= self.subway.MAX_TRAIN_MINUTES
            ]
            windowed = windowed[:max(self.subway.MIN_TRAIN_COUNT, len(windowed))]
            windowed = sorted(windowed, key=lambda t: self._get_train_display_minutes(t, now))
            return windowed[:min(max_trains, len(windowed))]

        return (
            filter_trains(f_trains, self.subway.MAX_TRAIN_COUNT),
            filter_trains(g_trains, self.subway.MAX_G_TRAIN_COUNT),
        )

    def _draw_next_trains(self, draw: ImageDraw.ImageDraw, next_f_trains: List[TrainArrival], next_g_trains: List[TrainArrival], now: datetime):
        """Draw the F and G train circles with their upcoming arrival times."""
        # Calculate dimensions
        circle_radius = self.subway.LOGO_RADIUS
        text_area_width = self.display.MAIN_SECTION_WIDTH - (
            self.subway.LOGO_CENTER_X + circle_radius + self.subway.TEXT_MARGIN
        )

        # Draw each train line section
        self._draw_train_line_section(
            draw=draw,
            trains=next_f_trains,
            route_id=config.TRAIN_LINE_1,
            logo_center_y=self.subway.F_TRAIN_Y,
            circle_radius=circle_radius,
            text_area_width=text_area_width,
            now=now
        )

        self._draw_train_line_section(
            draw=draw,
            trains=next_g_trains,
            route_id=config.TRAIN_LINE_2,
            logo_center_y=self.subway.G_TRAIN_Y,
            circle_radius=circle_radius,
            text_area_width=text_area_width,
            now=now
        )

    def _draw_train_line_section(self, draw: ImageDraw.ImageDraw, trains: List[TrainArrival],
                                route_id: str, logo_center_y: int,
                                circle_radius: int, text_area_width: int, now: datetime):
        """Draw a complete train line section with logo and arrival times"""
        # Draw the train line logo using the configured column position
        self._draw_train_line_logo(
            draw=draw,
            line_letter=route_id,
            x=self.display.ICON_COLUMN_X,  # Use configured position
            y=logo_center_y,
            radius=circle_radius
        )

        # Calculate text start position (just after the logo)
        text_start_x = self.subway.TEXT_START_X

        # Draw arrival times with increased line height
        line_height = self.subway.LINE_HEIGHT

        offset = self.subway.TEXT_BASE_OFFSETS.get(len(trains), self.subway.TEXT_BASE_DEFAULT_OFFSET)
        text_base_y = logo_center_y + offset

        for i, train in enumerate(trains):
            y = text_base_y + (i * (line_height + self.subway.LINE_SPACING)) - line_height
            self._draw_train_arrival_time(
                draw=draw,
                train=train,
                x=text_start_x,
                y=y,
                max_width=text_area_width,
                now=now
            )

    def _draw_train_arrival_time(self, draw: ImageDraw.ImageDraw, train: TrainArrival,
                                x: int, y: int, max_width: int, now: datetime):
        """Draw a train arrival time with minutes, 'min', and arrival time"""
        time_font = fonts.get('xheader')
        small_font = fonts.get('small')
        display_minutes = self._get_train_display_minutes(train, now)

        # Split arrival time into components
        arrival_hour = datetime.strptime(train.arrival_time, "%I:%M %p")
        hour_str = arrival_hour.strftime("%I:%M")
        ampm_str = arrival_hour.strftime("%p").lower()

        # Calculate all text widths
        min_text = "min"
        min_bbox = draw.textbbox((0, 0), min_text, font=small_font)
        min_width = min_bbox[2] - min_bbox[0]

        minutes_width = time_font.getlength(str(display_minutes))
        hour_width = time_font.getlength(hour_str)
        ampm_width = small_font.getlength(ampm_str)

        # Calculate total width and right-align the entire block
        total_width = minutes_width + 5 + min_width + 40 + hour_width + 5 + ampm_width
        start_x = x + max_width - total_width

        # Draw minutes until arrival
        draw.text(
            (start_x, y),
            str(display_minutes),
            font=time_font,
            fill=0,
            anchor="ls"
        )

        # Draw "min"
        draw.text(
            (start_x + minutes_width + 5, y),
            min_text,
            font=small_font,
            fill=0,
            anchor="ls"
        )

        # Draw arrival time
        time_x = start_x + minutes_width + min_width + 20
        draw.text(
            (time_x, y),
            hour_str,
            font=time_font,
            fill=0,
            anchor="ls"
        )

        # Draw am/pm
        draw.text(
            (time_x + hour_width, y),
            ampm_str,
            font=small_font,
            fill=0,
            anchor="ls"
        )

    def _draw_train_line_logo(self, draw: ImageDraw.ImageDraw, line_letter: str,
                             x: int, y: int, radius: int):
        """Draw a subway train line logo"""
        draw.ellipse(
            (x - radius, y - radius, x + radius, y + radius),
            fill=0  # Black circle
        )
        draw.text(
            (x, y),
            line_letter,
            font=fonts.get('xheader'),
            fill=255,  # White text
            anchor="mm"
        )

    def _minutes_to_next_train(self, trains: List[TrainArrival], now: datetime) -> Optional[int]:
        """Minutes until the soonest upcoming train across both lines, or None.

        Considers all trains in the feed (not just the display window), so the
        no-trains message can say how long the gap is even when the next train
        is further out than the arrivals list shows. Returns None when nothing
        is upcoming.
        """
        upcoming = [self._get_train_display_minutes(t, now) for t in trains]
        upcoming = [m for m in upcoming if m >= 1]
        return min(upcoming) if upcoming else None

    def _no_trains_message(self, minutes_to_next: Optional[int]) -> str:
        """Phrase the no-trains notice based on the gap until the next train."""
        if minutes_to_next is None or minutes_to_next > 240:  # indefinite or > 4 hours
            return "F & G trains are not currently running"
        if minutes_to_next < 100:
            return f"No trains for the next {minutes_to_next} minutes"
        hours = (minutes_to_next + 30) // 60  # round to nearest hour
        return f"No trains for the next {hours} hours"

    def _draw_no_trains(self, draw: ImageDraw.ImageDraw, trains: List[TrainArrival], now: datetime):
        """Draw the no-trains state: keep the F & G logos, with a status line
        at the bottom of the train pane describing when trains resume.
        """
        radius = self.subway.LOGO_RADIUS
        self._draw_train_line_logo(draw, config.TRAIN_LINE_1, self.display.ICON_COLUMN_X, self.subway.F_TRAIN_Y, radius)
        self._draw_train_line_logo(draw, config.TRAIN_LINE_2, self.display.ICON_COLUMN_X, self.subway.G_TRAIN_Y, radius)

        message = self._no_trains_message(self._minutes_to_next_train(trains, now))
        center_x = self.display.MAIN_SECTION_WIDTH // 2
        baseline_y = self.display.TRAIN_SECTION_Y + self.display.TRAIN_SECTION_HEIGHT - 30
        draw.text((center_x, baseline_y), message, font=fonts.get('medium'), fill=0, anchor="ms")

    def _draw_service_unavailable_message(self, draw: ImageDraw.ImageDraw):
        """Draw message when the train feeds could not be reached.

        Distinct from the no-trains message: this means we have no data, not
        that there are no trains.
        """
        draw.text(
            (self.subway.PADDING_X, self.subway.NEXT_TRAIN_Y),
            "Service",
            font=fonts.get('large'),
            fill=0
        )
        draw.text(
            (self.subway.PADDING_X, self.subway.NEXT_TRAIN_Y + 40),
            "unavailable",
            font=fonts.get('large'),
            fill=0
        )
        draw.text(
            (self.subway.PADDING_X, self.subway.LIST_Y),
            "Train data feed unreachable",
            font=fonts.get('medium'),
            fill=0
        )
