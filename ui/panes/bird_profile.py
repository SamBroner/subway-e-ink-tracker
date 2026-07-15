"""Full-screen profile for the most recent bird observation."""

from datetime import datetime
from pathlib import Path

from PIL import Image, ImageOps

from config.config import config
from data.models import BirdObservation, BirdResult
from ui.fonts import fonts
from ui.panes.base import Pane, PaneSurface, RenderContext
from ui.panes.bird_art import BirdArtLoader


class BirdProfilePane(Pane):
    """Show one recent bird large, with identifying metadata."""

    def __init__(self, rect: tuple[int, int, int, int], asset_dir: Path | str | None = None):
        super().__init__(rect)
        self._art_loader = BirdArtLoader(asset_dir)

    def paint(self, surface: PaneSurface, ctx: RenderContext):
        birds = ctx.data.birds
        if birds is None or not birds.observations:
            if birds is None:
                message = "Bird data loading"
            else:
                message = "BirdNET unreachable" if birds.source_unavailable else "No bird profile"
            surface.text(
                (self.w // 2, self.h // 2),
                message,
                font=fonts.get("large"),
                fill=0,
                anchor="mm",
            )
            return

        observation = birds.observations[0]
        self._draw_art(surface, observation)
        self._draw_text(surface, observation, birds)

    def _draw_art(self, surface: PaneSurface, observation: BirdObservation) -> None:
        art = self._art_loader.load(observation.sci_name, variant="mixed")
        target_box = (84, 70, self.w - 84, 570)
        x0, y0, x1, y1 = target_box
        target_size = (x1 - x0, y1 - y0)

        if art is None:
            surface.ellipse((230, 130, 595, 495), outline=0, width=3)
            initials = "".join(part[:1] for part in observation.common_name.split()[:2]).upper() or "?"
            surface.text((self.w // 2, 312), initials, font=fonts.get("xheader"), fill=0, anchor="mm")
            return

        image = ImageOps.contain(art.gray, target_size, method=Image.Resampling.LANCZOS)
        mask = ImageOps.contain(art.alpha, target_size, method=Image.Resampling.LANCZOS)
        x = x0 + (target_size[0] - image.width) // 2
        y = y0 + (target_size[1] - image.height) // 2
        surface.paste(image, (x, y), mask)

    def _draw_text(self, surface: PaneSurface, observation: BirdObservation, birds: BirdResult) -> None:
        center_x = self.w // 2
        self._draw_fit_text(surface, (center_x, 640), observation.common_name, fonts.get("xxlarge"), self.w - 96, anchor="ms")
        self._draw_fit_text(surface, (center_x, 688), observation.sci_name, fonts.get("large"), self.w - 96, anchor="ms")

        meta = f"{observation.count} {self._count_noun(observation.count)} in last {birds.window_hours}h"
        if observation.last_seen:
            meta += f" / last {self._format_last_seen(observation.last_seen)}"
        if observation.max_confidence is not None:
            meta += f" / {round(observation.max_confidence * 100)}% conf"
        self._draw_fit_text(surface, (center_x, 746), meta, fonts.get("medium"), self.w - 96, anchor="ms")

        surface.line((64, 790, self.w - 64, 790), fill=0, width=2)

    def _draw_fit_text(self, surface: PaneSurface, xy: tuple[int, int], text: str, font, max_width: int, anchor: str) -> None:
        surface.text(xy, self._fit_text(surface, text, font, max_width), font=font, fill=0, anchor=anchor)

    def _fit_text(self, surface: PaneSurface, text: str, font, max_width: int) -> str:
        if surface.textlength(text, font=font) <= max_width:
            return text
        suffix = "..."
        available = max(0, max_width - int(surface.textlength(suffix, font=font)))
        trimmed = text
        while trimmed and surface.textlength(trimmed, font=font) > available:
            trimmed = trimmed[:-1]
        return trimmed.rstrip() + suffix

    def _format_last_seen(self, value: str) -> str:
        try:
            dt = datetime.fromisoformat(value)
        except ValueError:
            try:
                dt = datetime.strptime(value, "%Y-%m-%d %H:%M:%S")
            except ValueError:
                return value
        return dt.strftime("%b %d %I:%M %p").replace(" 0", " ")

    def _count_noun(self, count: int) -> str:
        return "detection" if count == 1 else "detections"
