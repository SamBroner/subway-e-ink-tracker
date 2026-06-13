"""Full-screen bird observations pane."""

from datetime import datetime
from pathlib import Path

from PIL import Image, ImageOps

from config.config import config
from data.models import BirdObservation, BirdResult
from ui.fonts import fonts
from ui.panes.bird_art import BirdArtLoader
from ui.panes.base import Pane, PaneSurface, RenderContext


class BirdPane(Pane):
    """Render recent BirdNET observations with matching cutout illustrations."""

    def __init__(self, rect: tuple[int, int, int, int], asset_dir: Path | str | None = None):
        super().__init__(rect)
        self._art_loader = BirdArtLoader(asset_dir)

    def paint(self, surface: PaneSurface, ctx: RenderContext):
        birds = ctx.data.birds
        self._draw_header(surface, birds)

        if birds is None:
            self._draw_empty_state(surface, "Bird data loading")
            return
        if not birds.observations:
            message = "BirdNET unreachable" if birds.source_unavailable else f"No birds heard in {birds.window_hours}h"
            self._draw_empty_state(surface, message)
            return

        observations = birds.observations[:5]
        self._draw_featured_observation(surface, observations[0])
        for idx, observation in enumerate(observations[1:5]):
            self._draw_grid_observation(surface, observation, idx)

    def _draw_header(self, surface: PaneSurface, birds: BirdResult | None) -> None:
        title_font = fonts.get("xheader")
        small_font = fonts.get("small")
        surface.text((36, 78), "Birds heard", font=title_font, fill=0, anchor="ls")

        window_hours = birds.window_hours if birds else config.BIRD_WINDOW_HOURS
        surface.text((self.w - 36, 48), f"last {window_hours}h", font=small_font, fill=0, anchor="rs")
        if birds and birds.source_unavailable:
            surface.text((self.w - 36, 80), "BirdNET offline", font=small_font, fill=0, anchor="rs")
        surface.line((30, 112, self.w - 30, 112), fill=0, width=2)

    def _draw_featured_observation(self, surface: PaneSurface, observation: BirdObservation) -> None:
        art_box = (42, 145, 370, 475)
        self._draw_art(surface, observation, art_box)

        text_x = 398
        max_width = self.w - text_x - 36
        self._draw_fit_text(
            surface,
            (text_x, 222),
            observation.common_name,
            fonts.get("xlarge"),
            max_width,
            anchor="ls",
        )
        self._draw_fit_text(
            surface,
            (text_x, 268),
            observation.sci_name,
            fonts.get("medium"),
            max_width,
            anchor="ls",
        )

        count_text = self._count_text(observation.count)
        surface.text((text_x, 348), count_text, font=fonts.get("xheader"), fill=0, anchor="ls")
        meta = self._meta_text(observation)
        self._draw_fit_text(surface, (text_x, 402), meta, fonts.get("medium"), max_width, anchor="ls")

        surface.line((30, 520, self.w - 30, 520), fill=0, width=2)

    def _draw_grid_observation(self, surface: PaneSurface, observation: BirdObservation, index: int) -> None:
        col = index % 2
        row = index // 2
        x = 38 + col * 395
        y = 558 + row * 300
        slot_w = 350

        if col == 1:
            surface.line((self.w // 2, y - 24, self.w // 2, y + 240), fill=0, width=1)

        art_box = (x, y, x + 130, y + 130)
        self._draw_art(surface, observation, art_box)

        text_x = x + 148
        max_width = slot_w - 148
        name_font = fonts.get("medium")
        if surface.textlength(observation.common_name, font=name_font) > max_width:
            name_font = fonts.get("small")
        self._draw_fit_text(
            surface,
            (text_x, y + 28),
            observation.common_name,
            name_font,
            max_width,
            anchor="ls",
        )
        self._draw_fit_text(
            surface,
            (text_x, y + 56),
            observation.sci_name,
            fonts.get("small"),
            max_width,
            anchor="ls",
        )
        self._draw_fit_text(
            surface,
            (text_x, y + 88),
            self._count_text(observation.count),
            fonts.get("medium"),
            max_width,
            anchor="ls",
        )
        self._draw_fit_text(
            surface,
            (text_x, y + 122),
            self._meta_text(observation, compact=True),
            fonts.get("small"),
            max_width,
            anchor="ls",
        )

        surface.line((x, y + 192, x + slot_w, y + 192), fill=0, width=1)

    def _draw_empty_state(self, surface: PaneSurface, message: str) -> None:
        surface.text((self.w // 2, self.h // 2), message, font=fonts.get("large"), fill=0, anchor="mm")

    def _draw_art(self, surface: PaneSurface, observation: BirdObservation, box: tuple[int, int, int, int]) -> None:
        art = self._art_loader.load(observation.sci_name, variant="mixed")
        x0, y0, x1, y1 = box
        target_size = (x1 - x0, y1 - y0)
        if art is None:
            radius = min(target_size) // 2 - 8
            cx = x0 + target_size[0] // 2
            cy = y0 + target_size[1] // 2
            surface.ellipse((cx - radius, cy - radius, cx + radius, cy + radius), outline=0, width=2)
            initials = "".join(part[:1] for part in observation.common_name.split()[:2]).upper() or "?"
            surface.text((cx, cy), initials, font=fonts.get("xlarge"), fill=0, anchor="mm")
            return

        fitted_image = ImageOps.contain(art.gray, target_size, method=Image.Resampling.LANCZOS)
        fitted_mask = ImageOps.contain(art.alpha, target_size, method=Image.Resampling.LANCZOS)
        x = x0 + (target_size[0] - fitted_image.width) // 2
        y = y0 + (target_size[1] - fitted_image.height) // 2
        surface.paste(fitted_image, (x, y), fitted_mask)

    def _draw_fit_text(
        self,
        surface: PaneSurface,
        xy: tuple[int, int],
        text: str,
        font,
        max_width: int,
        anchor: str = "ls",
    ) -> None:
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

    def _count_text(self, count: int) -> str:
        noun = "detection" if count == 1 else "detections"
        return f"{count} {noun}"

    def _meta_text(self, observation: BirdObservation, compact: bool = False) -> str:
        parts = []
        if observation.last_seen:
            parts.append(self._format_last_seen(observation.last_seen, compact=compact))
        if observation.max_confidence is not None:
            label = f"{round(observation.max_confidence * 100)}%"
            parts.append(label if compact else f"{label} conf")
        return " / ".join(parts)

    def _format_last_seen(self, value: str, compact: bool = False) -> str:
        try:
            dt = datetime.fromisoformat(value)
        except ValueError:
            try:
                dt = datetime.strptime(value, "%Y-%m-%d %H:%M:%S")
            except ValueError:
                return value

        if compact:
            return dt.strftime("%I:%M %p").lstrip("0")
        return dt.strftime("%b %d %I:%M %p").replace(" 0", " ")
