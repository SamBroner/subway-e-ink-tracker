"""Unit tests for the no-trains message phrasing and its thresholds.

  - < 100 min  -> "No Trains for the next {x} minutes"
  - >= 100 min -> "No Trains for the next {x} hours" (rounded to nearest hour)
  - indefinite (None) or > 4 hours (240 min) -> "...not currently running"
"""

from ui.panes import SubwayPane

# The message logic lives on SubwayPane; a dummy rect is fine for these pure tests.
pane = SubwayPane((0, 0, 0, 0))

RUNNING = "F & G trains are not currently running"


def test_indefinite():
    assert pane._no_trains_message(None) == RUNNING


def test_minutes_branch():
    assert pane._no_trains_message(1) == "No trains for the next 1 minutes"
    assert pane._no_trains_message(55) == "No trains for the next 55 minutes"
    assert pane._no_trains_message(99) == "No trains for the next 99 minutes"


def test_hours_branch():
    assert pane._no_trains_message(100) == "No trains for the next 2 hours"
    assert pane._no_trains_message(130) == "No trains for the next 2 hours"
    assert pane._no_trains_message(150) == "No trains for the next 3 hours"
    assert pane._no_trains_message(240) == "No trains for the next 4 hours"


def test_beyond_four_hours_is_not_running():
    assert pane._no_trains_message(241) == RUNNING
    assert pane._no_trains_message(600) == RUNNING
