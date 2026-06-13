"""In-memory rendered-frame cache and background prewarmer."""

from __future__ import annotations

from collections import OrderedDict
from dataclasses import fields, is_dataclass
from datetime import datetime
import logging
import threading
from typing import Any, Callable, Optional

from PIL import Image

from data.models import AppData


logger = logging.getLogger(__name__)


Renderer = Callable[[AppData, Optional[datetime], Optional[str]], Image.Image]
RenderKey = tuple[Any, ...]


class RenderCache:
    """Small LRU cache for fully rendered screen images.

    The cache is intentionally in-memory only. It keeps button-driven screen
    transitions fast without introducing filesystem lifecycle or stale-file
    cleanup concerns.
    """

    def __init__(self, max_entries: int = 24):
        self.max_entries = max_entries
        self._frames: OrderedDict[RenderKey, Image.Image] = OrderedDict()
        self._lock = threading.RLock()
        self._render_lock = threading.RLock()
        self._generation = 0
        self._request: _PrewarmRequest | None = None
        self._worker: threading.Thread | None = None
        self._active_signature: tuple[RenderKey, ...] | None = None
        self._pending_signature: tuple[RenderKey, ...] | None = None
        self._completed_signature: tuple[RenderKey, ...] | None = None

    def get_or_render(
        self,
        app_data: AppData,
        now: Optional[datetime],
        screen_name: Optional[str],
        renderer: Renderer,
        *,
        cacheable: bool = True,
    ) -> Image.Image:
        if not cacheable:
            with self._render_lock:
                return renderer(app_data, now=now, screen_name=screen_name)

        key = self.key_for(app_data, now, screen_name, renderer)
        cached = self.get(key)
        if cached is not None:
            logger.debug("Render cache hit for %s", screen_name)
            return cached

        with self._render_lock:
            cached = self.get(key)
            if cached is not None:
                logger.debug("Render cache hit for %s after waiting", screen_name)
                return cached

            logger.debug("Render cache miss for %s", screen_name)
            image = renderer(app_data, now=now, screen_name=screen_name)
            self.put(key, image)
            return image.copy()

    def get(self, key: RenderKey) -> Image.Image | None:
        with self._lock:
            image = self._frames.get(key)
            if image is None:
                return None
            self._frames.move_to_end(key)
            return image.copy()

    def contains(self, key: RenderKey) -> bool:
        with self._lock:
            return key in self._frames

    def put(self, key: RenderKey, image: Image.Image) -> None:
        with self._lock:
            self._frames[key] = image.copy()
            self._frames.move_to_end(key)
            while len(self._frames) > self.max_entries:
                self._frames.popitem(last=False)

    def key_for(
        self,
        app_data: AppData,
        now: Optional[datetime],
        screen_name: Optional[str],
        renderer: Renderer,
    ) -> RenderKey:
        renderer_key = id(renderer)
        if screen_name in {"bird-collage", "bird-collage-named", "birds", "bird-profile"}:
            return (renderer_key, screen_name, "birds", _freeze(app_data.birds))

        if screen_name == "transit":
            return (
                renderer_key,
                screen_name,
                _displayed_clock(now),
                _freeze(app_data.weather),
                _freeze(app_data.subway),
                _freeze(app_data.bikes),
            )

        return (
            renderer_key,
            screen_name,
            _displayed_clock(now),
            _freeze(app_data),
        )

    def prewarm(
        self,
        app_data: AppData,
        now: Optional[datetime],
        screen_names: list[str],
        renderer: Renderer,
    ) -> None:
        keys = tuple(self.key_for(app_data, now, screen_name, renderer) for screen_name in screen_names)
        if not keys:
            return

        with self._lock:
            if (
                keys == self._active_signature
                or keys == self._pending_signature
                or (
                    keys == self._completed_signature
                    and all(key in self._frames for key in keys)
                )
            ):
                return
            self._generation += 1
            generation = self._generation
            self._pending_signature = keys
            self._request = _PrewarmRequest(
                generation=generation,
                app_data=app_data,
                now=now,
                screen_names=tuple(screen_names),
                renderer=renderer,
                signature=keys,
            )
            if self._worker is None or not self._worker.is_alive():
                self._worker = threading.Thread(target=self._prewarm_loop, name="render-prewarm")
                self._worker.daemon = True
                self._worker.start()

    def wait_for_idle(self, timeout: float = 5.0) -> bool:
        worker = self._worker
        if worker is None:
            return True
        worker.join(timeout)
        return not worker.is_alive()

    def clear(self) -> None:
        with self._lock:
            self._frames.clear()
            self._generation += 1
            self._request = None
            self._active_signature = None
            self._pending_signature = None
            self._completed_signature = None

    def _prewarm_loop(self) -> None:
        while True:
            with self._lock:
                request = self._request
                self._request = None
                if request is None:
                    self._active_signature = None
                    self._pending_signature = None
                    return
                self._active_signature = request.signature
                self._pending_signature = None

            completed = True
            logger.debug("Starting render prewarm for %s", ", ".join(request.screen_names))
            for screen_name in request.screen_names:
                with self._lock:
                    if request.generation != self._generation:
                        completed = False
                        break

                key = self.key_for(request.app_data, request.now, screen_name, request.renderer)
                if self.contains(key):
                    continue

                try:
                    with self._render_lock:
                        with self._lock:
                            if request.generation != self._generation:
                                completed = False
                                break
                        if self.contains(key):
                            continue
                        image = request.renderer(
                            request.app_data,
                            now=request.now,
                            screen_name=screen_name,
                        )
                except Exception:
                    logger.exception("Error prewarming render cache for %s", screen_name)
                    completed = False
                    continue

                with self._lock:
                    if request.generation != self._generation:
                        completed = False
                        break
                    self.put(key, image)

            with self._lock:
                if completed and request.generation == self._generation:
                    self._completed_signature = request.signature


class _PrewarmRequest:
    def __init__(
        self,
        *,
        generation: int,
        app_data: AppData,
        now: Optional[datetime],
        screen_names: tuple[str, ...],
        renderer: Renderer,
        signature: tuple[RenderKey, ...],
    ):
        self.generation = generation
        self.app_data = app_data
        self.now = now
        self.screen_names = screen_names
        self.renderer = renderer
        self.signature = signature


def _displayed_clock(now: Optional[datetime]) -> str:
    if now is None:
        return ""
    return now.strftime("%I:%M:%S%p")


def _freeze(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if is_dataclass(value):
        return (
            value.__class__.__name__,
            tuple((field.name, _freeze(getattr(value, field.name))) for field in fields(value)),
        )
    if isinstance(value, dict):
        return tuple(
            (str(key), _freeze(item))
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        )
    if isinstance(value, (list, tuple)):
        return tuple(_freeze(item) for item in value)
    if isinstance(value, (set, frozenset)):
        return tuple(sorted((_freeze(item) for item in value), key=repr))
    return repr(value)
