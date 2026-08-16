import json
import logging
import shlex
import subprocess
import threading
import time
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from typing import Callable

from config.config import config
from data.models import BirdObservation, BirdResult


logger = logging.getLogger(__name__)


def _project_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _resolve_project_path(path: str) -> Path:
    candidate = Path(path)
    if candidate.is_absolute():
        return candidate
    return _project_root() / candidate


def _remote_quote_path(path: str) -> str:
    """Quote a remote sqlite path while preserving leading ~/ expansion."""
    if path.startswith("~/"):
        rest = path[2:]
        return "~/" + shlex.quote(rest)
    return shlex.quote(path)


class BirdService:
    def __init__(self, now: Callable[[], datetime] | None = None):
        self.ssh_host = config.BIRDNET_SSH_HOST
        self.db_path = config.BIRDNET_DB_PATH
        self.window_hours = config.BIRD_WINDOW_HOURS
        self.rollover_lookback_minutes = config.BIRD_ROLLOVER_LOOKBACK_MINUTES
        self.mock_data_path = _resolve_project_path(config.BIRD_MOCK_DATA)
        self.use_mock_data = config.BIRD_USE_MOCK_DATA
        self.request_timeout_seconds = 20
        self.result_limit = config.BIRD_RESULT_LIMIT
        self._now = now or datetime.now
        self._subscribers: list[Callable[[BirdResult], None]] = []
        self._update_thread: threading.Thread | None = None
        self._should_run = False
        self._stop_event = threading.Event()
        self._current_result: BirdResult | None = None
        self._current_hour: str | None = None

    def subscribe(self, callback: Callable[[BirdResult], None]) -> None:
        self._subscribers.append(callback)
        if self._current_result is not None:
            callback(self._current_result)

    def start_updates(self, interval_seconds: int = 60) -> None:
        if self._update_thread and self._update_thread.is_alive():
            logger.warning("Bird update thread already running")
            return

        self._should_run = True
        self._stop_event.clear()
        self._update_thread = threading.Thread(target=self._update_loop, args=(interval_seconds,))
        self._update_thread.daemon = True
        self._update_thread.start()
        logger.info("Started bird update thread with %ss interval", interval_seconds)

    def stop_updates(self) -> None:
        self._should_run = False
        self._stop_event.set()
        if self._update_thread:
            self._update_thread.join()
            self._update_thread = None
        logger.info("Stopped bird updates")

    def _update_loop(self, interval_seconds: int) -> None:
        while self._should_run:
            try:
                previous_result = self._current_result
                result = self.get_bird_observations()
                if self._should_notify(result, previous_result):
                    self._notify_subscribers(result)
                self._current_result = result
                if self._stop_event.wait(self._seconds_until_next_update(interval_seconds)):
                    break
            except Exception as e:
                logger.error("Error in bird update loop: %s", e, exc_info=True)
                if self._stop_event.wait(self._seconds_until_next_update(interval_seconds)):
                    break

    def _seconds_until_next_update(self, interval_seconds: int) -> float:
        """Align periodic fetches to wall-clock boundaries, including HH:00."""
        interval_seconds = max(1, interval_seconds)
        remainder = time.time() % interval_seconds
        return interval_seconds - remainder if remainder else float(interval_seconds)

    def _should_notify(self, result: BirdResult, previous_result: BirdResult | None = None) -> bool:
        return result != previous_result

    def _notify_subscribers(self, result: BirdResult) -> None:
        for subscriber in self._subscribers:
            try:
                subscriber(result)
            except Exception as e:
                logger.error("Error notifying bird subscriber: %s", e, exc_info=True)

    def get_bird_observations(self) -> BirdResult:
        try:
            raw_result = self._load_mock_result() if self.use_mock_data else self._fetch_live_result()
            result = self._stabilize_current_hour(raw_result)
            self._current_result = result
            return result
        except Exception as e:
            logger.error("Error getting bird observations: %s", e, exc_info=True)
            if self._current_result is not None:
                return replace(self._current_result, source_unavailable=True)
            return BirdResult(
                observations=[],
                window_hours=self.window_hours,
                source_unavailable=True,
            )

    def _stabilize_current_hour(self, result: BirdResult) -> BirdResult:
        """Keep the current hour additive, then replace it at the next hour.

        The query window begins 15 minutes before the current hour. During the
        hour, existing observations retain their order and render-affecting
        metadata; only newly observed species are appended. This keeps existing
        collage placements stable for fast e-ink updates.
        """
        current_hour = self._now().strftime("%Y-%m-%d %H")
        if self._current_result is None or self._current_hour != current_hour:
            self._current_hour = current_hour
            return result

        observations = list(self._current_result.observations)
        seen = {self._observation_key(observation) for observation in observations}
        stable_max_count = max(
            (observation.count for observation in observations),
            default=None,
        )
        for observation in result.observations:
            key = self._observation_key(observation)
            if key in seen:
                continue
            if stable_max_count is not None and observation.count > stable_max_count:
                observation = replace(observation, count=stable_max_count)
            observations.append(observation)
            seen.add(key)
            if len(observations) >= self.result_limit:
                break

        return replace(
            result,
            observations=observations[:self.result_limit],
        )

    def _observation_key(self, observation: BirdObservation) -> tuple[str, str]:
        return (observation.sci_name, observation.common_name)

    def _load_mock_result(self) -> BirdResult:
        with self.mock_data_path.open() as f:
            payload = json.load(f)
        return self._parse_result_payload(payload)

    def _fetch_live_result(self) -> BirdResult:
        sql = self._summary_query()
        remote_command = (
            f"sqlite3 -json {_remote_quote_path(self.db_path)} {shlex.quote(sql)}"
        )
        completed = subprocess.run(
            ["ssh", "-o", "BatchMode=yes", self.ssh_host, remote_command],
            capture_output=True,
            check=True,
            text=True,
            timeout=self.request_timeout_seconds,
        )
        rows = json.loads(completed.stdout or "[]")
        return self._parse_sql_rows(rows)

    def _summary_query(self) -> str:
        lookback_minutes = max(0, int(self.rollover_lookback_minutes))
        limit = max(1, int(self.result_limit))
        return f"""
SELECT
  COALESCE(NULLIF(Sci_Name, ''), '') AS sci_name,
  COALESCE(NULLIF(Com_Name, ''), 'Unknown') AS common_name,
  COUNT(*) AS count,
  MAX(Date || ' ' || Time) AS last_seen,
  MAX(Confidence) AS max_confidence
FROM detections
WHERE datetime(Date || ' ' || Time) >= datetime(
  'now', 'localtime', 'start of hour', '-{lookback_minutes} minutes'
)
GROUP BY Sci_Name, Com_Name
ORDER BY last_seen DESC, count DESC
LIMIT {limit};
""".strip()

    def _parse_result_payload(self, payload: dict) -> BirdResult:
        observations = [
            self._parse_observation(row)
            for row in payload.get("observations", [])
        ]
        return BirdResult(
            observations=observations,
            window_hours=int(payload.get("window_hours", self.window_hours)),
            source_unavailable=bool(payload.get("source_unavailable", False)),
        )

    def _parse_sql_rows(self, rows: list[dict]) -> BirdResult:
        return BirdResult(
            observations=[self._parse_observation(row) for row in rows],
            window_hours=self.window_hours,
            source_unavailable=False,
        )

    def _parse_observation(self, row: dict) -> BirdObservation:
        confidence = row.get("max_confidence", row.get("Confidence"))
        if confidence is not None:
            confidence = float(confidence)

        return BirdObservation(
            sci_name=str(row.get("sci_name", row.get("Sci_Name", "")) or ""),
            common_name=str(row.get("common_name", row.get("Com_Name", "Unknown")) or "Unknown"),
            count=int(row.get("count", row.get("Count", 0)) or 0),
            last_seen=str(row.get("last_seen", row.get("Last_Seen", "")) or ""),
            max_confidence=confidence,
        )


bird_service = BirdService()
