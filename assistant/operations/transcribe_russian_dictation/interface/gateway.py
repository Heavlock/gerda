from __future__ import annotations

from typing import Protocol


class Recognizer(Protocol):
    def duration(self, capture: str) -> float: ...
    def recognize(self, capture: str, *, with_vad: bool) -> str: ...
