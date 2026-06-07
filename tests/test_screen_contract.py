from dataclasses import replace
from datetime import datetime, timedelta

from PIL import Image, ImageChops

from config.config import config
from data import AppData
from services.subway_service import TrainArrival
from services.subway_service import SubwayResult
from ui.panes import RenderContext
from ui.screens import BIRD_IMAGE_PATHS, screen_manager


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


def test_screen_requirements():
    assert screen_manager.get("transit").requires() == {"weather", "subway"}
    assert screen_manager.get("hello").requires() == set()
    for index in range(1, 6):
        assert screen_manager.get(f"bird-{index}").requires() == set()


def test_screen_order_includes_bird_images():
    assert screen_manager.names() == [
        "transit",
        "hello",
        "bird-1",
        "bird-2",
        "bird-3",
        "bird-4",
        "bird-5",
    ]


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


def test_hello_never_requests_regular_redraws():
    hello = screen_manager.get("hello")
    prev = _ctx()
    current = _ctx(now=prev.now + timedelta(minutes=5))
    assert not hello.should_redraw(current, prev)


def test_bird_screen_renders_static_image_without_data():
    bird = screen_manager.get("bird-1")
    ctx = RenderContext(data=AppData(), now=datetime(2026, 1, 15, 14, 23, 0))

    rendered = bird.render(ctx)
    with Image.open(BIRD_IMAGE_PATHS[0]) as source:
        expected = source.convert("L").rotate(180)

    assert rendered.size == (config.display.WIDTH, config.display.HEIGHT)
    assert ImageChops.difference(rendered, expected).getbbox() is None
