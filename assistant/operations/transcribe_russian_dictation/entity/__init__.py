from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Input:
    capture: str


@dataclass(frozen=True)
class Result:
    text: str


class RecognitionError(Exception):
    """The recording could not be recognized safely."""
