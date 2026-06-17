"""Shared bird illustration loading helpers."""

from dataclasses import dataclass
import logging
from pathlib import Path
import re
from typing import Literal

from PIL import Image, ImageFilter, ImageOps

from config.config import config


_ROOT_DIR = Path(__file__).resolve().parent.parent.parent
logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class BirdArt:
    path: Path
    rgba: Image.Image
    gray: Image.Image
    alpha: Image.Image


@dataclass(frozen=True)
class BirdArtTile:
    path: Path
    rgba: Image.Image
    gray: Image.Image
    alpha: Image.Image
    collision_mask: Image.Image
    dilated_collision_mask: Image.Image


def slugify_sci_name(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")


def resolve_bird_asset_dir() -> Path:
    configured = Path(config.BIRD_ASSET_DIR)
    if configured.is_absolute():
        return configured
    return _ROOT_DIR / configured


class BirdArtLoader:
    """Load bird cutout art by scientific name and cache cropped assets."""

    def __init__(self, asset_dir: Path | str | None = None):
        self.asset_dir = Path(asset_dir) if asset_dir is not None else resolve_bird_asset_dir()
        self._cache: dict[tuple[str, str], BirdArt | None] = {}
        self._tile_cache: dict[tuple[str, str, int], BirdArtTile | None] = {}

    def load(
        self,
        sci_name: str,
        variant: Literal["base", "alternate", "mixed"] = "base",
        index: int | None = None,
    ) -> BirdArt | None:
        slug = slugify_sci_name(sci_name)
        cache_key = (slug, variant)
        if cache_key in self._cache:
            return self._cache[cache_key]

        for candidate in self._candidate_paths(slug, variant):
            if candidate.exists():
                try:
                    with Image.open(candidate) as source:
                        rgba = source.convert("RGBA")
                        alpha = rgba.getchannel("A")
                        bbox = alpha.getbbox()
                        if bbox:
                            rgba = rgba.crop(bbox)
                        alpha = rgba.getchannel("A")
                        gray = ImageOps.grayscale(rgba)
                except OSError as exc:
                    logger.warning("Unable to load bird art %s: %s", candidate, exc)
                    continue
                self._cache[cache_key] = BirdArt(
                    path=candidate,
                    rgba=rgba,
                    gray=gray,
                    alpha=alpha,
                )
                return self._cache[cache_key]

        self._cache[cache_key] = None
        return None

    def load_tile(
        self,
        sci_name: str,
        *,
        variant: Literal["base", "alternate", "mixed"] = "mixed",
        target_width: int,
        gap: int = 7,
        index: int | None = None,
    ) -> BirdArtTile | None:
        slug = slugify_sci_name(sci_name)
        target_width = max(1, int(target_width))
        cache_key = (slug, variant, target_width)
        if cache_key in self._tile_cache:
            return self._tile_cache[cache_key]

        art = self.load(sci_name, variant=variant, index=index)
        if art is None:
            self._tile_cache[cache_key] = None
            return None

        target_height = max(1, round(art.rgba.height * target_width / art.rgba.width))
        rgba = art.rgba.resize((target_width, target_height), Image.Resampling.LANCZOS)
        alpha = rgba.getchannel("A")
        gray = ImageOps.grayscale(rgba)
        collision_mask = alpha.point(lambda p: 255 if p > 40 else 0)
        filter_size = max(3, 2 * max(1, int(gap)) + 1)
        dilated_collision_mask = collision_mask.filter(ImageFilter.MaxFilter(filter_size))
        self._tile_cache[cache_key] = BirdArtTile(
            path=art.path,
            rgba=rgba,
            gray=gray,
            alpha=alpha,
            collision_mask=collision_mask,
            dilated_collision_mask=dilated_collision_mask,
        )
        return self._tile_cache[cache_key]

    def _candidate_paths(
        self,
        slug: str,
        variant: Literal["base", "alternate", "mixed"],
    ) -> tuple[Path, Path]:
        base = self.asset_dir / f"{slug}.png"
        alternate = self.asset_dir / f"{slug}-2.png"

        if variant == "base":
            return (base, alternate)
        if variant == "alternate":
            return (alternate, base)
        if variant == "mixed":
            seed = sum(ord(ch) for ch in slug)
            return (alternate, base) if seed % 2 else (base, alternate)
        raise ValueError(f"Unknown bird art variant: {variant}")
