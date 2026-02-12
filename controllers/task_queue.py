from __future__ import annotations

import threading
from collections.abc import Callable


class TaskQueue:
    """Runs background tasks on daemon threads to keep UI responsive."""

    def __init__(self) -> None:
        self._threads: list[threading.Thread] = []

    def run(self, target: Callable[[], None]) -> None:
        """Start a new daemon thread for the given callable."""
        thread = threading.Thread(target=target, daemon=True)
        thread.start()
        self._threads.append(thread)
