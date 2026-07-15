"""Full-screen bird illustration collage panes."""

import logging
import math
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFont

from data.models import BirdObservation, BirdResult
from ui.fonts import fonts
from ui.panes.base import Pane, PaneSurface, RenderContext
from ui.panes.bird_art import BirdArtLoader, BirdArtTile


logger = logging.getLogger(__name__)


Rect = tuple[int, int, int, int]


@dataclass(frozen=True)
class LabelLayout:
    lines: tuple[str, ...]
    font: ImageFont.FreeTypeFont | ImageFont.ImageFont
    chip_size: tuple[int, int]
    text_size: tuple[int, int]
    padding: int
    line_gap: int
    font_size: int


@dataclass(frozen=True)
class LegendEntry:
    number: int
    common_name: str
    box: Rect


@dataclass(frozen=True)
class Placement:
    observation: BirdObservation
    bird_box: Rect
    label_box: Rect | None = None
    label_lines: tuple[str, ...] = ()
    bird_origin: tuple[int, int] = (0, 0)
    bird_mask: Image.Image | None = None
    number: int | None = None
    number_box: Rect | None = None
    label_kind: str = "none"


@dataclass(frozen=True)
class PlacementSpec:
    probe: Image.Image
    bird_offset: tuple[int, int]
    tile: BirdArtTile
    label_layout: LabelLayout | None = None
    label_offset: tuple[int, int] | None = None
    number: int | None = None


class BirdCollagePane(Pane):
    """Render up to 15 recent bird species as a packed cutout collage."""

    GAP = 7
    UNLABELED_MIN_WIDTH = 65
    NAMED_MIN_WIDTH = 56
    BASE_MIN_WIDTH = 95
    UNLABELED_MAX_WIDTH = 350
    NAMED_MAX_WIDTH = 325
    NAMED_SIZE_STEPS = (1.00, 0.92, 0.84, 0.76, 0.68, 0.60)
    LABEL_ANCHOR_GAP = 4

    def __init__(
        self,
        rect: tuple[int, int, int, int],
        asset_dir: Path | str | None = None,
        *,
        named: bool = False,
    ):
        super().__init__(rect)
        self.named = named
        self._art_loader = BirdArtLoader(asset_dir)
        self._cached_key: tuple | None = None
        self._cached_image: Image.Image | None = None
        self._last_placements: list[Placement] = []
        self._last_legend_entries: list[LegendEntry] = []
        self._occupied_boxes: list[Rect] = []

    def paint(self, surface: PaneSurface, ctx: RenderContext):
        key = self._cache_key(ctx.data.birds)
        if self._cached_image is None or key != self._cached_key:
            self._cached_image = self._build_collage(ctx.data.birds)
            self._cached_key = key

        surface.paste(self._cached_image, (self.x, self.y))

    def _cache_key(self, birds: BirdResult | None) -> tuple:
        if birds is None:
            return (None, self.named)
        return (
            self.named,
            birds.window_hours,
            birds.source_unavailable,
            tuple(
                (
                    obs.sci_name,
                    obs.common_name,
                    obs.count,
                    obs.last_seen,
                    obs.max_confidence,
                )
                for obs in birds.observations[:15]
            ),
        )

    def _build_collage(self, birds: BirdResult | None) -> Image.Image:
        self._last_placements = []
        self._last_legend_entries = []
        self._occupied_boxes = []
        canvas = Image.new("L", (self.w, self.h), 255)
        if self.w <= 0 or self.h <= 0:
            return canvas
        if birds is None:
            self._draw_empty_state(canvas, "Bird data loading")
            return canvas
        if not birds.observations:
            message = (
                "BirdNET unreachable"
                if birds.source_unavailable
                else f"No birds heard in {birds.window_hours}h"
            )
            self._draw_empty_state(canvas, message)
            return canvas

        observations = birds.observations[:15]
        max_count = max(1, max(max(1, observation.count) for observation in observations))
        if self.named:
            return self._build_named_collage(observations, max_count)
        return self._build_unlabeled_collage(observations, max_count)

    def _draw_empty_state(self, canvas: Image.Image, message: str) -> None:
        draw = ImageDraw.Draw(canvas)
        draw.text(
            (self.w // 2, self.h // 2),
            message,
            font=fonts.get("large"),
            fill=0,
            anchor="mm",
        )

    def _build_unlabeled_collage(
        self,
        observations: list[BirdObservation],
        max_count: int,
    ) -> Image.Image:
        canvas = Image.new("L", (self.w, self.h), 255)
        occupancy = Image.new("L", (self.w, self.h), 0)
        self._occupied_boxes = []

        for observation in observations:
            target_width = self._target_width(observation, max_count)
            placed = False
            for width in self._unlabeled_widths(target_width):
                tile = self._art_loader.load_tile(
                    observation.sci_name,
                    variant="mixed",
                    target_width=width,
                    gap=self.GAP,
                )
                if tile is None:
                    logger.debug(
                        "Skipping bird collage observation without art: %s (%s)",
                        observation.common_name,
                        observation.sci_name,
                    )
                    placed = True
                    break
                spec = PlacementSpec(
                    probe=tile.dilated_collision_mask,
                    bird_offset=(0, 0),
                    tile=tile,
                )
                if self._place_spec(canvas, occupancy, observation, spec):
                    placed = True
                    break

            if not placed:
                tile = self._smallest_tile(observation, named=False)
                if tile is not None:
                    spec = PlacementSpec(
                        probe=tile.dilated_collision_mask,
                        bird_offset=(0, 0),
                        tile=tile,
                    )
                    self._place_least_bad(canvas, occupancy, observation, spec)

        return canvas

    def _build_named_collage(
        self,
        observations: list[BirdObservation],
        max_count: int,
    ) -> Image.Image:
        attached = self._attempt_named_attached_pass(observations, max_count)
        if attached is not None:
            return attached
        return self._build_named_with_legend(observations, max_count)

    def _attempt_named_attached_pass(
        self,
        observations: list[BirdObservation],
        max_count: int,
    ) -> Image.Image | None:
        canvas = Image.new("L", (self.w, self.h), 255)
        occupancy = Image.new("L", (self.w, self.h), 0)
        placements_before = list(self._last_placements)
        occupied_boxes_before = list(self._occupied_boxes)
        self._occupied_boxes = []

        for observation in observations:
            if not self._place_named_attached(canvas, occupancy, observation, max_count):
                self._last_placements = placements_before
                self._occupied_boxes = occupied_boxes_before
                return None

        return canvas

    def _build_named_with_legend(
        self,
        observations: list[BirdObservation],
        max_count: int,
    ) -> Image.Image:
        self._last_placements = []
        self._last_legend_entries = []
        self._occupied_boxes = []
        canvas = Image.new("L", (self.w, self.h), 255)
        occupancy = Image.new("L", (self.w, self.h), 0)
        legend_rect = self._legend_rect()
        if legend_rect is not None:
            legend_mask = Image.new("L", (legend_rect[2] - legend_rect[0], legend_rect[3] - legend_rect[1]), 255)
            occupancy.paste(legend_mask, legend_rect[:2], legend_mask)
            self._occupied_boxes.append(legend_rect)

        legend_items: list[tuple[int, BirdObservation]] = []
        legend_number = 1
        for observation in observations:
            if self._place_named_attached(canvas, occupancy, observation, max_count):
                continue

            tile = self._smallest_tile(observation, named=True)
            if tile is None:
                logger.debug(
                    "Skipping named bird collage observation without art: %s (%s)",
                    observation.common_name,
                    observation.sci_name,
                )
                continue

            spec = PlacementSpec(
                probe=tile.dilated_collision_mask,
                bird_offset=(0, 0),
                tile=tile,
                number=legend_number,
            )
            self._place_least_bad(canvas, occupancy, observation, spec)
            legend_items.append((legend_number, observation))
            legend_number += 1

        if legend_rect is not None and legend_items:
            self._draw_legend(canvas, legend_rect, legend_items)
        return canvas

    def _place_named_attached(
        self,
        canvas: Image.Image,
        occupancy: Image.Image,
        observation: BirdObservation,
        max_count: int,
    ) -> bool:
        target_width = self._target_width(observation, max_count)
        missing_art = False

        for width in self._named_widths(target_width):
            tile = self._art_loader.load_tile(
                observation.sci_name,
                variant="mixed",
                target_width=width,
                gap=self.GAP,
            )
            if tile is None:
                missing_art = True
                break
            if self._place_named_tile(canvas, occupancy, observation, tile):
                return True

        if missing_art:
            logger.debug(
                "Skipping named bird collage observation without art: %s (%s)",
                observation.common_name,
                observation.sci_name,
            )
            return True
        return False

    def _place_named_tile(
        self,
        canvas: Image.Image,
        occupancy: Image.Image,
        observation: BirdObservation,
        tile: BirdArtTile,
    ) -> bool:
        specs = list(self._named_specs(tile, observation))
        if not specs:
            return False

        for bird_x, bird_y in self._spiral_positions(tile.dilated_collision_mask.size):
            if not self._can_place(tile.dilated_collision_mask, occupancy, bird_x, bird_y):
                continue

            for spec in specs:
                spec_x = bird_x - spec.bird_offset[0]
                spec_y = bird_y - spec.bird_offset[1]
                if self._can_place(spec.probe, occupancy, spec_x, spec_y):
                    self._commit_spec(canvas, occupancy, observation, spec, (spec_x, spec_y))
                    return True
        return False

    def _target_width(self, observation: BirdObservation, max_count: int) -> int:
        w_max = self.NAMED_MAX_WIDTH if self.named else self.UNLABELED_MAX_WIDTH
        scale = (max(1, observation.count) / max(1, max_count)) ** 0.65
        return int(self.BASE_MIN_WIDTH + (w_max - self.BASE_MIN_WIDTH) * scale)

    def _unlabeled_widths(self, target_width: int) -> list[int]:
        widths = []
        width = min(target_width, max(1, self.w - 2), max(1, self.h - 2))
        while width >= self.UNLABELED_MIN_WIDTH:
            widths.append(max(1, int(width)))
            width *= 0.9
        widths.append(min(widths[-1] if widths else target_width, self.UNLABELED_MIN_WIDTH))
        return self._dedupe_widths(widths)

    def _named_widths(self, target_width: int) -> list[int]:
        widths = [
            max(1, int(target_width * step))
            for step in self.NAMED_SIZE_STEPS
            if target_width * step >= self.NAMED_MIN_WIDTH
        ]
        if not widths:
            widths = [min(max(1, target_width), self.NAMED_MIN_WIDTH)]
        return self._dedupe_widths(widths)

    def _dedupe_widths(self, widths: list[int]) -> list[int]:
        seen = set()
        deduped = []
        for width in widths:
            if width not in seen:
                seen.add(width)
                deduped.append(width)
        return deduped

    def _smallest_tile(self, observation: BirdObservation, *, named: bool) -> BirdArtTile | None:
        min_width = self.NAMED_MIN_WIDTH if named else self.UNLABELED_MIN_WIDTH
        return self._art_loader.load_tile(
            observation.sci_name,
            variant="mixed",
            target_width=min_width,
            gap=self.GAP,
        )

    def _named_specs(
        self,
        tile: BirdArtTile,
        observation: BirdObservation,
    ):
        for layout in self._label_layouts(observation.common_name, tile.rgba.width):
            for label_x, label_y in self._label_offsets(tile.rgba.size, layout.chip_size):
                spec = self._build_named_spec(tile, layout, label_x, label_y)
                if spec is not None:
                    yield spec

    def _build_named_spec(
        self,
        tile: BirdArtTile,
        layout: LabelLayout,
        label_x: int,
        label_y: int,
    ) -> PlacementSpec | None:
        bw, bh = tile.collision_mask.size
        lw, lh = layout.chip_size
        expanded_label = (
            label_x - self.GAP,
            label_y - self.GAP,
            label_x + lw + self.GAP,
            label_y + lh + self.GAP,
        )
        min_x = min(0, expanded_label[0])
        min_y = min(0, expanded_label[1])
        max_x = max(bw, expanded_label[2])
        max_y = max(bh, expanded_label[3])
        probe_w = max_x - min_x
        probe_h = max_y - min_y
        if probe_w > self.w or probe_h > self.h:
            return None

        bird_offset = (-min_x, -min_y)
        label_offset = (label_x - min_x, label_y - min_y)
        expanded_label_offset = (expanded_label[0] - min_x, expanded_label[1] - min_y)
        combined = Image.new("L", (probe_w, probe_h), 0)
        combined.paste(tile.dilated_collision_mask, bird_offset, tile.dilated_collision_mask)
        expanded_label_size = (
            expanded_label[2] - expanded_label[0],
            expanded_label[3] - expanded_label[1],
        )
        label_mask = Image.new("L", expanded_label_size, 255)
        combined.paste(label_mask, expanded_label_offset, label_mask)
        return PlacementSpec(
            probe=combined,
            bird_offset=bird_offset,
            tile=tile,
            label_layout=layout,
            label_offset=label_offset,
        )

    def _place_spec(
        self,
        canvas: Image.Image,
        occupancy: Image.Image,
        observation: BirdObservation,
        spec: PlacementSpec,
    ) -> bool:
        position = self._find_spiral_position(spec.probe, occupancy)
        if position is None:
            return False
        self._commit_spec(canvas, occupancy, observation, spec, position)
        return True

    def _find_spiral_position(
        self,
        probe: Image.Image,
        occupancy: Image.Image,
    ) -> tuple[int, int] | None:
        for x, y in self._spiral_positions(probe.size):
            if self._can_place(probe, occupancy, x, y):
                return (x, y)

        return None

    def _spiral_positions(self, probe_size: tuple[int, int]):
        pw, ph = probe_size
        if pw > self.w or ph > self.h:
            return

        cx, cy = self.w // 2, self.h // 2
        ybias = self.h / self.w if self.w else 1
        theta = 0.0
        step = 0.32
        a = 3.0
        max_theta = max(360.0, math.hypot(self.w, self.h) / a + 80)

        while theta < max_theta:
            r = a * theta
            x = cx + int(r * math.cos(theta)) - pw // 2
            y = cy + int(r * ybias * math.sin(theta)) - ph // 2
            theta += step

            if 0 <= x <= self.w - pw and 0 <= y <= self.h - ph:
                yield (x, y)

    def _place_least_bad(
        self,
        canvas: Image.Image,
        occupancy: Image.Image,
        observation: BirdObservation,
        spec: PlacementSpec,
    ) -> bool:
        position = self._find_least_bad_position(spec.probe, occupancy)
        if position is None:
            return False
        self._commit_spec(canvas, occupancy, observation, spec, position)
        return True

    def _find_least_bad_position(
        self,
        probe: Image.Image,
        occupancy: Image.Image,
    ) -> tuple[int, int] | None:
        pw, ph = probe.size
        if pw > self.w or ph > self.h:
            return None

        edge_candidates = (
            (0, 0),
            ((self.w - pw) // 2, 0),
            (self.w - pw, 0),
            (0, (self.h - ph) // 2),
            (self.w - pw, (self.h - ph) // 2),
            (0, self.h - ph),
            ((self.w - pw) // 2, self.h - ph),
            (self.w - pw, self.h - ph),
        )
        grid_step = max(24, min(pw, ph) // 2)
        grid_candidates = [
            (x, y)
            for y in range(0, max(1, self.h - ph + 1), grid_step)
            for x in range(0, max(1, self.w - pw + 1), grid_step)
            if x in (0, self.w - pw) or y in (0, self.h - ph)
        ]

        best: tuple[int, tuple[int, int]] | None = None
        for x, y in (*edge_candidates, *grid_candidates):
            x = min(max(0, x), self.w - pw)
            y = min(max(0, y), self.h - ph)
            score = self._overlap_score(probe, occupancy, x, y)
            if score == 0:
                return (x, y)
            if best is None or score < best[0]:
                best = (score, (x, y))
        return best[1] if best else None

    def _can_place(self, probe: Image.Image, occupancy: Image.Image, x: int, y: int) -> bool:
        pw, ph = probe.size
        if not (0 <= x <= self.w - pw and 0 <= y <= self.h - ph):
            return False
        candidate_box = (x, y, x + pw, y + ph)
        if not any(self._overlaps(candidate_box, occupied) for occupied in self._occupied_boxes):
            return True
        region = occupancy.crop((x, y, x + pw, y + ph))
        return ImageChops.multiply(region, probe).getbbox() is None

    def _overlaps(self, a: Rect, b: Rect) -> bool:
        return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]

    def _overlap_score(self, probe: Image.Image, occupancy: Image.Image, x: int, y: int) -> int:
        pw, ph = probe.size
        region = occupancy.crop((x, y, x + pw, y + ph))
        overlap = ImageChops.multiply(region, probe)
        return sum(value * count for value, count in enumerate(overlap.histogram()))

    def _commit_spec(
        self,
        canvas: Image.Image,
        occupancy: Image.Image,
        observation: BirdObservation,
        spec: PlacementSpec,
        position: tuple[int, int],
    ) -> None:
        x, y = position
        bird_x = x + spec.bird_offset[0]
        bird_y = y + spec.bird_offset[1]
        canvas.paste(spec.tile.gray, (bird_x, bird_y), spec.tile.alpha)

        label_box = None
        label_lines: tuple[str, ...] = ()
        label_kind = "none"
        if spec.label_layout is not None and spec.label_offset is not None:
            label_x = x + spec.label_offset[0]
            label_y = y + spec.label_offset[1]
            label_box = self._draw_label(canvas, label_x, label_y, spec.label_layout)
            label_lines = spec.label_layout.lines
            label_kind = "attached"

        number_box = None
        if spec.number is not None:
            number_box = self._draw_number_chip(canvas, bird_x, bird_y, spec.number)
            label_kind = "legend"

        occupancy.paste(spec.probe, position, spec.probe)
        self._occupied_boxes.append((x, y, x + spec.probe.width, y + spec.probe.height))
        bird_box = self._opaque_bird_box(spec.tile.collision_mask, bird_x, bird_y, spec.tile.rgba.size)
        self._last_placements.append(
            Placement(
                observation=observation,
                bird_box=bird_box,
                label_box=label_box,
                label_lines=label_lines,
                bird_origin=(bird_x, bird_y),
                bird_mask=spec.tile.collision_mask,
                number=spec.number,
                number_box=number_box,
                label_kind=label_kind,
            )
        )

    def _opaque_bird_box(
        self,
        mask: Image.Image,
        x: int,
        y: int,
        tile_size: tuple[int, int],
    ) -> Rect:
        bbox = mask.getbbox()
        if bbox is None:
            return (x, y, x + tile_size[0], y + tile_size[1])
        return (x + bbox[0], y + bbox[1], x + bbox[2], y + bbox[3])

    def _label_offsets(
        self,
        tile_size: tuple[int, int],
        chip_size: tuple[int, int],
    ) -> tuple[tuple[int, int], ...]:
        tw, th = tile_size
        lw, lh = chip_size
        gap = self.LABEL_ANCHOR_GAP
        return (
            ((tw - lw) // 2, th + gap),               # below centered
            ((tw - lw) // 2, -lh - gap),              # above centered
            (-lw - gap, th - lh),                     # lower-left
            (tw + gap, th - lh),                      # lower-right
            (-lw - gap, 0),                           # upper-left
            (tw + gap, 0),                            # upper-right
            (-lw - gap, (th - lh) // 2),              # left centered
            (tw + gap, (th - lh) // 2),               # right centered
        )

    def _label_layouts(self, common_name: str, tile_width: int) -> list[LabelLayout]:
        max_width = min(self.w - 14, max(120, int(tile_width * 1.35)))
        if max_width <= 0:
            return []

        layouts: list[tuple[tuple[int, float, int], LabelLayout]] = []
        candidates = self._line_candidates(common_name)
        for font_size in range(18, 9, -1):
            font = self._label_font(font_size)
            for lines in candidates:
                layout = self._measure_label(lines, font, font_size)
                if layout.chip_size[0] > max_width:
                    continue
                widths = [self._text_block_size((line,), font)[0] for line in lines]
                balance = max(widths, default=0) - min(widths, default=0)
                score = (len(lines), balance, -font_size)
                layouts.append((score, layout))

        layouts.sort(key=lambda item: item[0])
        return [layout for _score, layout in layouts]

    def _line_candidates(self, common_name: str) -> tuple[tuple[str, ...], ...]:
        words = common_name.split()
        if len(words) <= 1:
            return ((common_name,),)

        candidates: list[tuple[str, ...]] = [(common_name,)]
        for split in range(1, len(words)):
            candidates.append((" ".join(words[:split]), " ".join(words[split:])))

        if len(words) >= 4:
            for first in range(1, len(words) - 1):
                for second in range(first + 1, len(words)):
                    candidates.append((
                        " ".join(words[:first]),
                        " ".join(words[first:second]),
                        " ".join(words[second:]),
                    ))

        deduped = []
        seen = set()
        for candidate in candidates:
            if candidate not in seen:
                seen.add(candidate)
                deduped.append(candidate)
        return tuple(deduped)

    def _measure_label(self, lines: tuple[str, ...], font, font_size: int) -> LabelLayout:
        padding = 4
        line_gap = 2
        text_w, text_h = self._text_block_size(lines, font, line_gap=line_gap)
        return LabelLayout(
            lines=lines,
            font=font,
            chip_size=(text_w + padding * 2, text_h + padding * 2),
            text_size=(text_w, text_h),
            padding=padding,
            line_gap=line_gap,
            font_size=font_size,
        )

    def _text_block_size(self, lines: tuple[str, ...], font, line_gap: int = 2) -> tuple[int, int]:
        scratch = Image.new("L", (1, 1), 255)
        draw = ImageDraw.Draw(scratch)
        widths = []
        heights = []
        for line in lines:
            left, top, right, bottom = draw.textbbox((0, 0), line, font=font)
            widths.append(right - left)
            heights.append(bottom - top)
        return max(widths, default=0), sum(heights) + max(0, len(lines) - 1) * line_gap

    def _label_font(self, size: int):
        try:
            return ImageFont.truetype(fonts.font_path, size)
        except Exception:
            return fonts.get("small")

    def _draw_label(self, canvas: Image.Image, x: int, y: int, layout: LabelLayout) -> Rect:
        draw = ImageDraw.Draw(canvas)
        chip_w, chip_h = layout.chip_size
        draw.rectangle((x, y, x + chip_w, y + chip_h), fill=255)

        cursor_y = y + layout.padding
        for line in layout.lines:
            left, top, right, bottom = draw.textbbox((0, 0), line, font=layout.font)
            line_w = right - left
            tx = x + (chip_w - line_w) // 2 - left
            draw.text((tx, cursor_y - top), line, font=layout.font, fill=0)
            cursor_y += (bottom - top) + layout.line_gap

        return (x, y, x + chip_w, y + chip_h)

    def _draw_number_chip(self, canvas: Image.Image, bird_x: int, bird_y: int, number: int) -> Rect:
        draw = ImageDraw.Draw(canvas)
        font = self._label_font(14)
        text = str(number)
        left, top, right, bottom = draw.textbbox((0, 0), text, font=font)
        size = max(18, right - left + 8, bottom - top + 8)
        x = min(max(0, bird_x + 2), max(0, self.w - size))
        y = min(max(0, bird_y + 2), max(0, self.h - size))
        box = (x, y, x + size, y + size)
        draw.rectangle(box, fill=255, outline=0)
        draw.text((x + size // 2, y + size // 2), text, font=font, fill=0, anchor="mm")
        return box

    def _legend_rect(self) -> Rect | None:
        if self.w < 180 or self.h < 160:
            return None
        height = min(240, max(140, self.h // 5))
        return (0, self.h - height, self.w, self.h)

    def _draw_legend(
        self,
        canvas: Image.Image,
        rect: Rect,
        legend_items: list[tuple[int, BirdObservation]],
    ) -> None:
        draw = ImageDraw.Draw(canvas)
        x0, y0, x1, y1 = rect
        draw.rectangle(rect, fill=255)
        draw.line((x0, y0, x1, y0), fill=0, width=1)

        layout = self._legend_layout(legend_items, rect)
        for number, common_name, lines, font, box in layout:
            cursor_y = box[1]
            for line in lines:
                draw.text((box[0], cursor_y), line, font=font, fill=0)
                text_box = draw.textbbox((box[0], cursor_y), line, font=font)
                cursor_y += text_box[3] - text_box[1] + 2
            self._last_legend_entries.append(LegendEntry(number=number, common_name=common_name, box=box))

    def _legend_layout(
        self,
        legend_items: list[tuple[int, BirdObservation]],
        rect: Rect,
    ) -> list[tuple[int, str, tuple[str, ...], ImageFont.FreeTypeFont | ImageFont.ImageFont, Rect]]:
        x0, y0, x1, y1 = rect
        padding = 10
        available_w = max(1, x1 - x0 - padding * 2)
        available_h = max(1, y1 - y0 - padding * 2)
        for font_size in range(14, 9, -1):
            font = self._label_font(font_size)
            for columns in range(1, min(3, len(legend_items)) + 1):
                col_w = max(1, available_w // columns)
                rows = math.ceil(len(legend_items) / columns)
                entry_layouts = []
                max_col_heights = [0 for _ in range(columns)]
                for idx, (number, observation) in enumerate(legend_items):
                    col = min(columns - 1, idx // rows)
                    lines = self._wrap_legend_text(number, observation.common_name, font, col_w - 8)
                    line_h = self._text_block_size(("Ag",), font)[1] + 2
                    height = len(lines) * line_h + 4
                    max_col_heights[col] += height
                    entry_layouts.append((number, observation.common_name, lines, font, col, height))
                if max(max_col_heights, default=0) <= available_h:
                    positioned = []
                    col_y = [y0 + padding for _ in range(columns)]
                    for number, common_name, lines, font, col, height in entry_layouts:
                        x = x0 + padding + col * col_w
                        y = col_y[col]
                        positioned.append((number, common_name, lines, font, (x, y, x + col_w - 8, y + height)))
                        col_y[col] += height
                    return positioned

        font = self._label_font(10)
        col_w = max(1, available_w // 3)
        positioned = []
        col_y = [y0 + padding for _ in range(3)]
        for idx, (number, observation) in enumerate(legend_items):
            col = idx % 3
            lines = self._wrap_legend_text(number, observation.common_name, font, col_w - 8)
            line_h = self._text_block_size(("Ag",), font)[1] + 2
            height = len(lines) * line_h + 4
            x = x0 + padding + col * col_w
            y = col_y[col]
            positioned.append((number, observation.common_name, lines, font, (x, y, x + col_w - 8, y + height)))
            col_y[col] += height
        return positioned

    def _wrap_legend_text(
        self,
        number: int,
        common_name: str,
        font,
        max_width: int,
    ) -> tuple[str, ...]:
        draw = ImageDraw.Draw(Image.new("L", (1, 1), 255))
        prefix = f"{number} "
        lines = []
        current = prefix
        for word in common_name.split():
            candidate = f"{current}{word}" if current == prefix else f"{current} {word}"
            if draw.textlength(candidate, font=font) <= max_width or current == prefix:
                current = candidate
            else:
                lines.append(current)
                current = "  " + word
        lines.append(current)
        return tuple(lines)
