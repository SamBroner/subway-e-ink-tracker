"""Golden-view integration tests.

Renders each scenario in `scenarios.py` through the real layout engine
(`ui.layout.getImage`) at the fixed reference time and compares the result,
pixel-for-pixel, against a committed reference PNG in `golden_views/`.

Usage:
    # Compare against committed goldens (default; this is the regression gate):
    .venv/bin/python -m pytest tests/golden/test_golden_views.py

    # (Re)generate the golden PNGs, e.g. after an intentional visual change:
    GOLDEN_UPDATE=1 .venv/bin/python -m pytest tests/golden/test_golden_views.py
    #   ...or, as a plain script:
    .venv/bin/python -m tests.golden.test_golden_views

Comparison is exact: any differing pixel fails. On mismatch the freshly
rendered image is written next to the golden as `<name>.actual.png` for
side-by-side inspection.
"""

import os
from pathlib import Path

import pytest
from PIL import Image, ImageChops

from ui.layout import getImage
from tests.golden.fixtures import FIXED_NOW
from tests.golden.scenarios import all_scenarios, Scenario

GOLDEN_DIR = Path(__file__).parent / "golden_views"


def render_scenario(scenario: Scenario) -> Image.Image:
    """Render a scenario to the upright image a viewer/e-ink panel would show.

    `getImage` rotates 180° for the panel's physical orientation, and the
    display layer rotates again before showing it. We reproduce that second
    rotation here so goldens are right-side-up and natural to review.
    """
    _name, weather, trains, bikes = scenario
    img = getImage(weather, trains, bikes, now=FIXED_NOW)
    return img.rotate(180)


def write_golden(scenario: Scenario) -> Path:
    GOLDEN_DIR.mkdir(parents=True, exist_ok=True)
    name = scenario[0]
    path = GOLDEN_DIR / f"{name}.png"
    render_scenario(scenario).save(path)
    return path


@pytest.mark.parametrize("scenario", all_scenarios(), ids=lambda s: s[0])
def test_golden_view(scenario: Scenario):
    name = scenario[0]
    rendered = render_scenario(scenario)

    if os.environ.get("GOLDEN_UPDATE"):
        path = write_golden(scenario)
        pytest.skip(f"GOLDEN_UPDATE set; wrote {path}")

    golden_path = GOLDEN_DIR / f"{name}.png"
    assert golden_path.exists(), (
        f"Missing golden for '{name}'. Generate baselines with "
        f"GOLDEN_UPDATE=1 pytest, review them, then commit."
    )

    golden = Image.open(golden_path)
    assert rendered.size == golden.size, (
        f"Size mismatch for '{name}': rendered {rendered.size} vs golden {golden.size}"
    )

    # Normalise modes before diffing (PNG of an 'L' image loads back as 'L').
    if rendered.mode != golden.mode:
        golden = golden.convert(rendered.mode)

    diff = ImageChops.difference(rendered, golden)
    bbox = diff.getbbox()
    if bbox is not None:
        actual_path = GOLDEN_DIR / f"{name}.actual.png"
        rendered.save(actual_path)
        changed_pixels = sum(1 for px in diff.getdata() if px != 0)
        pytest.fail(
            f"Golden mismatch for '{name}': {changed_pixels} pixel(s) differ "
            f"within bbox {bbox}. Wrote rendered output to {actual_path}. "
            f"If this change is intentional, regenerate with GOLDEN_UPDATE=1."
        )


def main() -> None:
    """Regenerate all golden PNGs (bypasses pytest)."""
    for scenario in all_scenarios():
        path = write_golden(scenario)
        print(f"wrote {path}")


if __name__ == "__main__":
    main()
