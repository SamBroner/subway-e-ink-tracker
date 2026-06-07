"""Static full-screen image pane."""

from pathlib import Path

from PIL import Image, ImageOps

from ui.panes.base import Pane, PaneSurface, RenderContext


class StaticImagePane(Pane):
    """Paint a static image into the pane rect."""

    def __init__(self, rect: tuple[int, int, int, int], image_path: Path | str):
        super().__init__(rect)
        self.image_path = Path(image_path)
        self._image = self._load_image()

    def _load_image(self) -> Image.Image:
        with Image.open(self.image_path) as source:
            image = source.convert("L")

        if image.size == (self.w, self.h):
            return image

        fitted = ImageOps.contain(image, (self.w, self.h), method=Image.Resampling.LANCZOS)
        canvas = Image.new("L", (self.w, self.h), 255)
        x = (self.w - fitted.width) // 2
        y = (self.h - fitted.height) // 2
        canvas.paste(fitted, (x, y))
        return canvas

    def paint(self, surface: PaneSurface, ctx: RenderContext):
        surface.paste(self._image, (self.x, self.y))
