from __future__ import annotations

from contextlib import AbstractContextManager
from pathlib import Path
from typing import Protocol

from app.operations.transcribe_media.entity import Input, Result, SegmentData


class MediaGateway(Protocol):
    def discover(self, path: Path) -> list[Path]: ...

    def prepare_audio(self, source: Path) -> AbstractContextManager[Path]: ...

    def duration(self, audio_path: Path) -> float: ...


class TranscriberGateway(Protocol):
    def recognize_direct(self, audio_path: Path) -> str: ...

    def recognize_with_vad(self, audio_path: Path) -> list[SegmentData]: ...


class Repository(Protocol):
    def save(
        self,
        source_file: Path,
        duration: float,
        segments: list[SegmentData],
    ) -> None: ...


class ProgressGateway(Protocol):
    def report(self, message: str) -> None: ...


class Usecase(Protocol):
    def execute(self, input_data: Input) -> Result: ...


__all__ = [
    "MediaGateway",
    "ProgressGateway",
    "Repository",
    "TranscriberGateway",
    "Usecase",
]
