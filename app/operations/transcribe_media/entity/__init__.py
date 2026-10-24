from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class SegmentData:
    id: int
    start: float
    end: float
    text: str


@dataclass(frozen=True)
class Input:
    input_path: Path
    vad_mode: str
    auto_vad_seconds: float


@dataclass(frozen=True)
class Result:
    processed_files: tuple[Path, ...]
