from dataclasses import replace
from datetime import datetime, timedelta
import math
from pathlib import Path

from PIL import Image

from config.config import config
from data import AppData, BirdObservation, BirdResult
from services.subway_service import TrainArrival
from services.subway_service import SubwayResult
from ui.panes import BirdCollagePane, BirdPane, BirdProfilePane, RenderContext
from ui.panes.bird_art import BirdArtLoader
from ui.screens import build_bird_collage_screen, screen_manager


BIRD_ART_DIR = Path(__file__).parent / "fixtures" / "bird_art"


def _ctx(**overrides):
    base = RenderContext(
        data=AppData(
            weather={"current": {}},
            subway=SubwayResult(trains=[]),
        ),
        now=datetime(2026, 1, 15, 14, 23, 0),
    )
    return replace(base, **overrides)


def _train(train_id: str, minutes: int) -> TrainArrival:
    return TrainArrival(
        minutes_until_arrival=minutes,
        arrival_time="02:30 PM",
        arrival_timestamp=0,
        train_id=train_id,
        route_id=config.TRAIN_LINE_1,
    )


def _subway(trains=None, unavailable=False) -> SubwayResult:
    unavailable_lines = (
        frozenset({config.TRAIN_LINE_1, config.TRAIN_LINE_2})
        if unavailable
        else frozenset()
    )
    return SubwayResult(trains=trains or [], unavailable_lines=unavailable_lines)


def _observation(sci: str, common: str, count: int, minute: int = 40) -> BirdObservation:
    return BirdObservation(
        sci_name=sci,
        common_name=common,
        count=count,
        last_seen=f"2026-06-11 22:{minute:02d}:10",
        max_confidence=0.908,
    )


def _bird_fixtures(include_missing: bool = True) -> BirdResult:
    observations = [
        _observation("Turdus migratorius", "American Robin", 12, 59),
        _observation("Cyanocitta cristata", "Blue Jay", 10, 58),
        _observation("Poecile atricapillus", "Black-capped Chickadee", 9, 57),
        _observation("Dryobates pubescens", "Downy Woodpecker", 8, 56),
        _observation("Archilochus colubris", "Ruby-throated Hummingbird", 7, 55),
        _observation("Myiarchus crinitus", "Great Crested Flycatcher", 6, 54),
        _observation("Setophaga virens", "Black-throated Green Warbler", 5, 53),
        _observation("Sphyrapicus varius", "Yellow-bellied Sapsucker", 4, 52),
    ]
    if include_missing:
        observations.append(_observation("Imaginaris absentia", "Missing-art Species", 3, 51))
    return BirdResult(observations=observations, window_hours=24)


def _fifteen_bird_fixtures() -> BirdResult:
    return BirdResult(
        observations=[
            _observation("Poecile atricapillus", "Black-capped Chickadee", 1, 59),
            _observation("Turdus migratorius", "American Robin", 40, 58),
            _observation("Cyanocitta cristata", "Blue Jay", 30, 57),
            _observation("Dryobates pubescens", "Downy Woodpecker", 25, 56),
            _observation("Archilochus colubris", "Ruby-throated Hummingbird", 22, 55),
            _observation("Myiarchus crinitus", "Great Crested Flycatcher", 20, 54),
            _observation("Setophaga virens", "Black-throated Green Warbler", 18, 53),
            _observation("Sphyrapicus varius", "Yellow-bellied Sapsucker", 16, 52),
            _observation("Cardinalis cardinalis", "Northern Cardinal", 14, 51),
            _observation("Baeolophus bicolor", "Tufted Titmouse", 12, 50),
            _observation("Spinus tristis", "American Goldfinch", 10, 49),
            _observation("Dumetella carolinensis", "Gray Catbird", 8, 48),
            _observation("Zenaida macroura", "Mourning Dove", 6, 47),
            _observation("Melanerpes carolinus", "Red-bellied Woodpecker", 4, 46),
            _observation("Agelaius phoeniceus", "Red-winged Blackbird", 2, 45),
        ],
        window_hours=24,
    )


def _empty_birds(unavailable: bool = False) -> BirdResult:
    return BirdResult(observations=[], window_hours=24, source_unavailable=unavailable)


def _render_pane(pane, birds: BirdResult | None) -> Image.Image:
    frame = Image.new("L", (config.display.WIDTH, config.display.HEIGHT), 255)
    pane.render(
        frame,
        RenderContext(data=AppData(birds=birds), now=datetime(2026, 1, 15, 14, 23, 0)),
    )
    return frame


def _overlap(a, b) -> bool:
    return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]


def _center_distance(box) -> float:
    cx = (box[0] + box[2]) / 2
    cy = (box[1] + box[3]) / 2
    return math.hypot(cx - config.display.WIDTH / 2, cy - config.display.HEIGHT / 2)


def _label_overlaps_bird_alpha(label_box, placement) -> bool:
    if placement.bird_mask is None:
        return False
    bird_x, bird_y = placement.bird_origin
    mask_box = (
        bird_x,
        bird_y,
        bird_x + placement.bird_mask.width,
        bird_y + placement.bird_mask.height,
    )
    if not _overlap(label_box, mask_box):
        return False

    ix0 = max(label_box[0], mask_box[0])
    iy0 = max(label_box[1], mask_box[1])
    ix1 = min(label_box[2], mask_box[2])
    iy1 = min(label_box[3], mask_box[3])
    crop = placement.bird_mask.crop((ix0 - bird_x, iy0 - bird_y, ix1 - bird_x, iy1 - bird_y))
    return crop.getbbox() is not None


def test_screen_requirements_and_exact_order():
    assert screen_manager.names() == [
        "transit",
        "bird-collage-named",
        "birds",
        "bird-profile",
    ]
    assert "hello" not in screen_manager.names()
    assert "bird-collage" not in screen_manager.names()
    assert screen_manager.get("transit").requires() == {"weather", "subway"}
    for name in ("bird-collage-named", "birds", "bird-profile"):
        assert screen_manager.get(name).requires() == set()


def test_transit_redraws_when_displayed_time_changes():
    transit = screen_manager.get("transit")
    prev = _ctx()
    current = _ctx(now=prev.now + timedelta(seconds=1))
    assert transit.should_redraw(current, prev)


def test_transit_redraws_when_top_trains_change():
    transit = screen_manager.get("transit")
    prev = _ctx(data=AppData(
        weather={"current": {}},
        subway=_subway([_train("a", 3), _train("b", 9)]),
    ))
    current = _ctx(data=AppData(
        weather={"current": {}},
        subway=_subway([_train("c", 3), _train("b", 9)]),
    ))
    assert transit.should_redraw(current, prev)


def test_transit_redraws_when_subway_availability_changes():
    transit = screen_manager.get("transit")
    prev = _ctx(data=AppData(
        weather={"current": {}},
        subway=_subway(unavailable=False),
    ))
    current = _ctx(data=AppData(
        weather={"current": {}},
        subway=_subway(unavailable=True),
    ))
    assert transit.should_redraw(current, prev)


def test_bird_screens_redraw_when_observations_change():
    prev = _ctx(data=AppData(birds=_bird_fixtures(include_missing=False)))
    changed = _bird_fixtures(include_missing=False)
    current = _ctx(data=AppData(birds=BirdResult(
        observations=[
            replace(changed.observations[0], count=99),
            *changed.observations[1:],
        ],
        window_hours=24,
    )))

    assert build_bird_collage_screen().should_redraw(current, prev)
    for name in ("bird-collage-named", "birds", "bird-profile"):
        assert screen_manager.get(name).should_redraw(current, prev)


def test_unlabeled_collage_renders_without_labels():
    pane = BirdCollagePane(
        (0, 0, config.display.WIDTH, config.display.HEIGHT),
        asset_dir=BIRD_ART_DIR,
        named=False,
    )
    frame = _render_pane(pane, _bird_fixtures())

    assert frame.getextrema()[0] < 255
    assert pane._last_placements
    assert all(placement.label_box is None for placement in pane._last_placements)


def test_collage_draws_loading_and_empty_states(tmp_path):
    panes = [
        BirdCollagePane(
            (0, 0, config.display.WIDTH, config.display.HEIGHT),
            asset_dir=tmp_path,
            named=False,
        ),
        BirdCollagePane(
            (0, 0, config.display.WIDTH, config.display.HEIGHT),
            asset_dir=tmp_path,
            named=True,
        ),
    ]

    for pane in panes:
        for birds in (None, _empty_birds(), _empty_birds(unavailable=True)):
            frame = _render_pane(pane, birds)
            assert frame.size == (config.display.WIDTH, config.display.HEIGHT)
            assert frame.getextrema()[0] < 255


def test_unlabeled_collage_uses_recency_for_placement_and_count_for_size():
    pane = BirdCollagePane(
        (0, 0, config.display.WIDTH, config.display.HEIGHT),
        asset_dir=BIRD_ART_DIR,
        named=False,
    )
    _render_pane(pane, _fifteen_bird_fixtures())

    placements = pane._last_placements
    assert placements[0].observation.sci_name == "Poecile atricapillus"
    distances = [_center_distance(placement.bird_box) for placement in placements]
    assert distances[0] == min(distances)

    most_recent_width = placements[0].bird_box[2] - placements[0].bird_box[0]
    high_count_width = placements[1].bird_box[2] - placements[1].bird_box[0]
    assert high_count_width > most_recent_width


def test_named_collage_renders_full_common_names_without_ellipsis_and_allows_two_lines():
    pane = BirdCollagePane(
        (0, 0, config.display.WIDTH, config.display.HEIGHT),
        asset_dir=BIRD_ART_DIR,
        named=True,
    )
    frame = _render_pane(pane, _bird_fixtures(include_missing=False))

    assert frame.getextrema()[0] < 255
    label_texts = [" ".join(placement.label_lines) for placement in pane._last_placements]
    assert "Black-throated Green Warbler" in label_texts
    assert all(
        "..." not in line
        for placement in pane._last_placements
        for line in placement.label_lines
    )


def test_named_collage_supports_two_and_three_line_label_layouts():
    pane = BirdCollagePane(
        (0, 0, config.display.WIDTH, config.display.HEIGHT),
        named=True,
    )

    two_line_layouts = pane._label_layouts("Black-throated Green Warbler", 120)
    three_line_layouts = pane._label_layouts("Very Long Black-throated Green Warbler", 110)

    assert any(len(layout.lines) == 2 for layout in two_line_layouts)
    assert any(len(layout.lines) == 3 for layout in three_line_layouts)


def test_named_collage_places_most_recent_bird_closest_to_center():
    pane = BirdCollagePane(
        (0, 0, config.display.WIDTH, config.display.HEIGHT),
        asset_dir=BIRD_ART_DIR,
        named=True,
    )
    _render_pane(pane, _fifteen_bird_fixtures())

    placements = pane._last_placements
    assert placements[0].observation.sci_name == "Poecile atricapillus"
    distances = [_center_distance(placement.bird_box) for placement in placements]
    assert distances[0] == min(distances)


def test_named_collage_labels_stay_on_canvas_and_do_not_overlap_birds_or_labels():
    pane = BirdCollagePane(
        (0, 0, config.display.WIDTH, config.display.HEIGHT),
        asset_dir=BIRD_ART_DIR,
        named=True,
    )
    _render_pane(pane, _bird_fixtures(include_missing=False))

    placements = [placement for placement in pane._last_placements if placement.label_box is not None]
    assert placements
    for placement in placements:
        label_box = placement.label_box
        assert label_box is not None
        assert 0 <= label_box[0] < label_box[2] <= config.display.WIDTH
        assert 0 <= label_box[1] < label_box[3] <= config.display.HEIGHT
        assert not _label_overlaps_bird_alpha(label_box, placement)

    for idx, placement in enumerate(placements):
        assert placement.label_box is not None
        for other in placements[idx + 1:]:
            assert other.label_box is not None
            assert not _overlap(placement.label_box, other.label_box)
            assert not _label_overlaps_bird_alpha(placement.label_box, other)
            assert not _label_overlaps_bird_alpha(other.label_box, placement)


def test_named_collage_uses_legend_fallback_when_attached_labels_cannot_fit():
    observations = [
        replace(
            observation,
            common_name=f"Unbreakablylongfallbacklabelrequiringlegendfallback{idx}",
        )
        for idx, observation in enumerate(
            _bird_fixtures(include_missing=False).observations[:4],
            start=1,
        )
    ]
    birds = BirdResult(observations=observations, window_hours=24)
    pane = BirdCollagePane(
        (0, 0, 220, 320),
        asset_dir=BIRD_ART_DIR,
        named=True,
    )
    frame = _render_pane(pane, birds)

    assert frame.size == (config.display.WIDTH, config.display.HEIGHT)
    assert len(pane._last_placements) == len(observations)
    assert all(placement.label_kind == "legend" for placement in pane._last_placements)
    assert [entry.common_name for entry in pane._last_legend_entries] == [
        observation.common_name for observation in observations
    ]


def test_bird_list_screen_draws_only_five_and_includes_latin_names():
    pane = BirdPane(
        (0, 0, config.display.WIDTH, config.display.HEIGHT),
        asset_dir=BIRD_ART_DIR,
    )
    seen = []
    original_draw = pane._draw_fit_text

    def record_text(surface, xy, text, font, max_width, anchor="ls"):
        seen.append(text)
        original_draw(surface, xy, text, font, max_width, anchor)

    pane._draw_fit_text = record_text
    _render_pane(pane, _bird_fixtures())

    assert "Archilochus colubris" in seen
    assert "Great Crested Flycatcher" not in seen
    for observation in _bird_fixtures().observations[:5]:
        assert observation.sci_name in seen


def test_bird_list_screen_has_no_clipped_names():
    pane = BirdPane(
        (0, 0, config.display.WIDTH, config.display.HEIGHT),
        asset_dir=BIRD_ART_DIR,
    )
    frame = _render_pane(pane, _bird_fixtures())

    assert frame.size == (config.display.WIDTH, config.display.HEIGHT)
    assert frame.getextrema()[0] < 255


def test_bird_list_screen_uses_same_art_variant_as_collage():
    class RecordingLoader:
        def __init__(self):
            self.calls = []

        def load(self, sci_name, variant="base", index=None):
            self.calls.append((sci_name, variant, index))
            return None

    pane = BirdPane(
        (0, 0, config.display.WIDTH, config.display.HEIGHT),
        asset_dir=BIRD_ART_DIR,
    )
    loader = RecordingLoader()
    pane._art_loader = loader

    _render_pane(
        pane,
        BirdResult(observations=_bird_fixtures().observations[:1], window_hours=24),
    )

    assert loader.calls == [("Turdus migratorius", "mixed", None)]


def test_bird_profile_renders_most_recent_bird():
    pane = BirdProfilePane(
        (0, 0, config.display.WIDTH, config.display.HEIGHT),
        asset_dir=BIRD_ART_DIR,
    )
    seen = []
    original_draw = pane._draw_fit_text

    def record_text(surface, xy, text, font, max_width, anchor):
        seen.append(text)
        original_draw(surface, xy, text, font, max_width, anchor)

    pane._draw_fit_text = record_text
    frame = _render_pane(pane, _bird_fixtures())

    assert frame.getextrema()[0] < 255
    assert "American Robin" in seen
    assert "Turdus migratorius" in seen


def test_all_bird_screens_handle_empty_unavailable_and_missing_art(tmp_path):
    pane_specs = [
        BirdCollagePane(
            (0, 0, config.display.WIDTH, config.display.HEIGHT),
            asset_dir=tmp_path,
            named=False,
        ),
        BirdCollagePane(
            (0, 0, config.display.WIDTH, config.display.HEIGHT),
            asset_dir=tmp_path,
            named=True,
        ),
        BirdPane(
            (0, 0, config.display.WIDTH, config.display.HEIGHT),
            asset_dir=tmp_path,
        ),
        BirdProfilePane(
            (0, 0, config.display.WIDTH, config.display.HEIGHT),
            asset_dir=tmp_path,
        ),
    ]

    for pane in pane_specs:
        for birds in (_empty_birds(), _empty_birds(unavailable=True), _bird_fixtures()):
            frame = _render_pane(pane, birds)
            assert frame.size == (config.display.WIDTH, config.display.HEIGHT)


def test_art_loader_variant_policy_is_deterministic():
    loader = BirdArtLoader(asset_dir=BIRD_ART_DIR)

    base = loader.load("Poecile atricapillus", variant="base")
    alternate = loader.load("Poecile atricapillus", variant="alternate")
    mixed_a = loader.load("Poecile atricapillus", variant="mixed", index=0)
    mixed_b = loader.load("Poecile atricapillus", variant="mixed", index=99)

    assert base is not None and base.path.name == "poecile-atricapillus.png"
    assert alternate is not None and alternate.path.name == "poecile-atricapillus-2.png"
    assert mixed_a is not None
    assert mixed_a.path == mixed_b.path


def test_art_loader_reuses_resized_tile_cache():
    loader = BirdArtLoader(asset_dir=BIRD_ART_DIR)

    first = loader.load_tile("Poecile atricapillus", variant="mixed", target_width=120)
    second = loader.load_tile("Poecile atricapillus", variant="mixed", target_width=120)

    assert first is not None
    assert first is second
    assert first.collision_mask.getbbox() is not None
    assert first.dilated_collision_mask.getbbox() is not None


def test_art_loader_skips_unreadable_images(tmp_path):
    (tmp_path / "poecile-atricapillus.png").write_text("not a png")
    loader = BirdArtLoader(asset_dir=tmp_path)

    assert loader.load("Poecile atricapillus") is None
