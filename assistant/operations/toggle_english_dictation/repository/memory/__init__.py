from __future__ import annotations
import threading
from ...entity import Recording


class RecordingRepository:
    def __init__(self):
        self.lock = threading.Lock()
        self.active: Recording | None = None

    def acquire(self) -> bool:
        return self.lock.acquire(blocking=False)

    def release(self) -> None:
        self.lock.release()

    def get(self) -> Recording | None:
        return self.active

    def save(self, value: Recording | None) -> None:
        self.active = value
