"""
Local watchlist cache for edge-level alerting.

Periodically syncs the watchlist from the DRDO server and caches it locally.
When a plate is detected, it can be checked against this local cache
for instant alerting without network latency.
"""
from __future__ import annotations

import logging
import threading
import time
from typing import Optional

import requests

from edge.config import (
    EDGE_API_KEY,
    SERVER_URL,
    WATCHLIST_SYNC_INTERVAL_SECONDS,
)

LOGGER = logging.getLogger("anpr.edge.watchlist_cache")


class WatchlistCache:
    """Thread-safe local watchlist cache with periodic server sync."""

    def __init__(self):
        self._plates: set[str] = set()
        self._lock = threading.Lock()
        self._running = False
        self._sync_thread: Optional[threading.Thread] = None
        self._last_sync: float = 0
        self._version: int = 0

    def is_watchlist_hit(self, plate_number: str) -> bool:
        """Check if a plate is on the watchlist. Instant, no network call."""
        with self._lock:
            return plate_number.upper() in self._plates

    def get_all_plates(self) -> set[str]:
        with self._lock:
            return self._plates.copy()

    def start_sync(self) -> None:
        """Start the background sync thread."""
        self._running = True
        self._sync_thread = threading.Thread(
            target=self._sync_loop, name="watchlist-sync", daemon=True,
        )
        self._sync_thread.start()
        LOGGER.info("Watchlist sync started (interval=%ds).",
                     WATCHLIST_SYNC_INTERVAL_SECONDS)

    def stop(self) -> None:
        self._running = False
        if self._sync_thread:
            self._sync_thread.join(timeout=10)

    def force_sync(self) -> bool:
        """Trigger an immediate sync. Returns True on success."""
        return self._do_sync()

    def _sync_loop(self) -> None:
        # Do an initial sync immediately
        self._do_sync()

        while self._running:
            time.sleep(WATCHLIST_SYNC_INTERVAL_SECONDS)
            if not self._running:
                break
            self._do_sync()

    def _do_sync(self) -> bool:
        """Fetch the watchlist from the server and update the local cache."""
        try:
            resp = requests.get(
                f"{SERVER_URL}/api/edge/watchlist-sync",
                headers={"X-Edge-API-Key": EDGE_API_KEY},
                timeout=10,
            )
            if resp.status_code == 200:
                data = resp.json()
                plates = set(p.upper() for p in data.get("plates", []))
                version = data.get("version", 0)

                with self._lock:
                    old_count = len(self._plates)
                    self._plates = plates
                    self._version = version
                    self._last_sync = time.time()

                if len(plates) != old_count:
                    LOGGER.info(
                        "Watchlist synced: %d plates (was %d). Version: %d",
                        len(plates), old_count, version,
                    )
                return True
            else:
                LOGGER.warning("Watchlist sync failed: HTTP %d", resp.status_code)
                return False
        except requests.ConnectionError:
            LOGGER.debug("Server unreachable for watchlist sync.")
            return False
        except Exception as exc:
            LOGGER.warning("Watchlist sync error: %s", exc)
            return False
