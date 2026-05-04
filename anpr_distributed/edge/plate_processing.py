"""
Plate vote tracker and post-processing for the edge node.

Ported from legacy_backend.py PlateVoteTracker class, with additions:
  - Temporal deduplication (same plate, same camera, within 30s → skip)
  - Thread-safe for multi-camera usage
"""
from __future__ import annotations

import threading
import time
from collections import defaultdict

from shared.plate_utils import normalize_plate_text

LIVE_VOTE_MIN_HITS = 2
LIVE_VOTE_TTL = 30
DEDUP_WINDOW_SECONDS = 30.0


class PlateVoteTracker:
    """
    Tracks plate text votes over time to filter noise and confirm readings.
    A plate is only "confirmed" after min_hits consistent reads in the same
    spatial bucket.
    """

    def __init__(self, min_hits: int = LIVE_VOTE_MIN_HITS, ttl: int = LIVE_VOTE_TTL):
        self.min_hits = min_hits
        self.ttl = ttl
        self._tick = 0
        self._store: dict[tuple[str, int, int], dict] = {}
        self._lock = threading.Lock()

    def _bucket_key(self, source: str, bbox: tuple[int, int, int, int]) -> tuple[str, int, int]:
        x1, y1, x2, y2 = bbox
        cx = (x1 + x2) // 2
        cy = (y1 + y2) // 2
        return (source, cx // 80, cy // 40)

    def register(
        self,
        source: str,
        bbox: tuple[int, int, int, int],
        plate_text: str,
        confidence: float = 0.0,
    ) -> str | None:
        """
        Register a plate detection. Returns the confirmed plate text
        if vote threshold is met, otherwise None.
        """
        normalized = normalize_plate_text(plate_text)
        if not normalized:
            return None

        with self._lock:
            self._tick += 1
            key = self._bucket_key(source, bbox)
            slot = self._store.setdefault(
                key,
                {"votes": defaultdict(int), "best_conf": {}, "last_seen": self._tick},
            )
            slot["last_seen"] = self._tick
            slot["votes"][normalized] += 1
            slot["best_conf"][normalized] = max(
                float(confidence or 0.0),
                slot["best_conf"].get(normalized, 0.0),
            )
            self._prune()

            best_text, best_hits = max(
                slot["votes"].items(),
                key=lambda item: (item[1], slot["best_conf"].get(item[0], 0.0), item[0]),
            )
            if best_hits >= self.min_hits:
                return best_text
        return None

    def _prune(self) -> None:
        cutoff = self._tick - self.ttl
        stale = [k for k, v in self._store.items() if v["last_seen"] < cutoff]
        for k in stale:
            self._store.pop(k, None)


class TemporalDeduplicator:
    """
    Prevents re-logging the same plate from the same camera within a
    time window. The old system lacked this — PlateVoteTracker only gates
    on confirmation, not re-logging.
    """

    def __init__(self, window_seconds: float = DEDUP_WINDOW_SECONDS):
        self._window = window_seconds
        self._last_seen: dict[tuple[str, str], float] = {}
        self._lock = threading.Lock()

    def is_duplicate(self, camera_id: str, plate_number: str) -> bool:
        """Return True if this plate was already logged recently from this camera."""
        key = (camera_id, plate_number.upper())
        now = time.time()

        with self._lock:
            # Clean old entries
            cutoff = now - self._window
            self._last_seen = {
                k: t for k, t in self._last_seen.items() if t > cutoff
            }

            last_time = self._last_seen.get(key)
            if last_time is not None and (now - last_time) < self._window:
                return True

            self._last_seen[key] = now
            return False
