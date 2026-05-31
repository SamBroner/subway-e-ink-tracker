"""Unit tests for the subway service-availability distinction.

These cover the rule that decides "service unavailable" vs "no trains"
without any network: a SubwayResult is "service unavailable" only when *every*
configured line feed failed to fetch.
"""

from config.config import config
from services.subway_service import SubwayResult

F = config.TRAIN_LINE_1
G = config.TRAIN_LINE_2


def test_no_failures_is_available():
    assert SubwayResult(trains=[], unavailable_lines=frozenset()).service_unavailable is False


def test_single_line_down_is_still_available():
    # One feed up (even if it returned no trains) is a real picture, not an outage.
    assert SubwayResult(trains=[], unavailable_lines=frozenset({F})).service_unavailable is False
    assert SubwayResult(trains=[], unavailable_lines=frozenset({G})).service_unavailable is False


def test_all_lines_down_is_unavailable():
    assert SubwayResult(trains=[], unavailable_lines=frozenset({F, G})).service_unavailable is True


def test_trains_present_with_one_line_down_is_available():
    result = SubwayResult(trains=["sentinel"], unavailable_lines=frozenset({F}))
    assert result.service_unavailable is False
