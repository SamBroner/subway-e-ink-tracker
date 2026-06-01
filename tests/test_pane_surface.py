"""Unit tests for PaneSurface (and Pane.render compositing).

These pin the two properties the pane layer relies on:
  1. Translation: content drawn at a global coordinate lands at
     `global - origin` inside the tile.
  2. Clipping: content whose translated position falls outside the tile is
     silently dropped — never drawn out of place, never raised.

Goldens only exercise this indirectly, and only for in-bounds content, so a
sign error in the translation or a broken clip could otherwise slip through.
"""

from PIL import Image, ImageDraw

from ui.fonts import fonts
from ui.panes.base import Pane, PaneSurface, RenderContext


def _white(w, h):
    return Image.new('L', (w, h), 255)


# --- translation --------------------------------------------------------------

def test_pt_and_box_math():
    surf = PaneSurface(_white(10, 10), (5, 7))
    assert surf._pt((8, 10)) == (3, 3)
    assert surf._box((5, 7, 15, 17)) == (0, 0, 10, 10)


def test_paste_is_translated_by_origin():
    tile = _white(100, 100)
    surf = PaneSurface(tile, (50, 60))
    surf.paste(Image.new('L', (4, 4), 0), (70, 80))  # global (70,80) -> tile (20,20)
    assert tile.getpixel((20, 20)) == 0      # landed at translated position
    assert tile.getpixel((70, 80)) == 255    # not at the raw global position


def test_line_is_translated_by_origin():
    tile = _white(100, 100)
    surf = PaneSurface(tile, (10, 20))
    # vertical line, global (40,30)->(40,70)  =>  tile column x=30, y=10..50
    surf.line((40, 30, 40, 70), fill=0)
    assert tile.getpixel((30, 30)) == 0      # on the translated line
    assert tile.getpixel((40, 30)) == 255    # not on the untranslated column
    assert tile.getpixel((30, 5)) == 255     # above the line's translated extent


# --- clipping -----------------------------------------------------------------

def test_paste_straddling_edge_is_clipped():
    tile = _white(100, 100)
    surf = PaneSurface(tile, (50, 60))
    # 10x10 black at global (45,55) -> tile (-5,-5): only the lower-right 5x5 lands
    surf.paste(Image.new('L', (10, 10), 0), (45, 55))
    assert tile.getpixel((0, 0)) == 0        # in-bounds corner drawn
    assert tile.getpixel((4, 4)) == 0
    assert tile.getpixel((5, 5)) == 255      # just past the clipped square


def test_fully_out_of_bounds_draw_is_dropped():
    tile = _white(100, 100)
    surf = PaneSurface(tile, (0, 0))
    surf.line((1000, 1000, 1100, 1100), fill=0)  # entirely outside the tile
    surf.paste(Image.new('L', (5, 5), 0), (500, 500))
    assert tile.getextrema() == (255, 255)   # still all white; nothing drawn, no error


# --- documented gotchas -------------------------------------------------------

def test_textbbox_returns_tile_local_coords():
    tile = _white(200, 80)
    font = fonts.get('small')
    surf = PaneSurface(tile, (5, 7))
    raw = ImageDraw.Draw(tile).textbbox((10, 10), "Hi", font=font)
    # global anchor (15,17) with origin (5,7) -> tile-local (10,10)
    assert surf.textbbox((15, 17), "Hi", font=font) == raw


def test_textbbox_width_is_origin_invariant():
    tile = _white(200, 80)
    font = fonts.get('small')
    b0 = PaneSurface(tile, (0, 0)).textbbox((0, 0), "Hi", font=font)
    b1 = PaneSurface(tile, (30, 40)).textbbox((30, 40), "Hi", font=font)
    assert (b1[2] - b1[0]) == (b0[2] - b0[0])  # callers depend on bbox widths


def test_textlength_is_passthrough():
    tile = _white(200, 80)
    font = fonts.get('small')
    surf = PaneSurface(tile, (33, 44))
    assert surf.textlength("Hello", font=font) == ImageDraw.Draw(tile).textlength("Hello", font=font)


# --- Pane.render round-trip ---------------------------------------------------

def test_render_composites_tile_at_rect():
    """A pane drawing at a global coord inside its rect lands at that coord in
    the frame (tile translate then paste-back is the identity for in-bounds)."""

    class _DotPane(Pane):
        def paint(self, surface, ctx):
            surface.line((60, 65, 60, 68), fill=0)  # global coords within the rect

    frame = _white(200, 200)
    _DotPane((50, 60, 30, 30)).render(frame, ctx=None)
    assert frame.getpixel((60, 65)) == 0     # drawn at the global coordinate
    assert frame.getpixel((60, 62)) == 255   # above the drawn segment
    assert frame.getpixel((10, 10)) == 255   # outside the pane's rect, untouched
