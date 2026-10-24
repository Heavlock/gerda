from __future__ import annotations

import os
from pathlib import Path

from app.operations.transcribe_media.entity import Input, Result
from app.operations.transcribe_media.interface import Usecase


def vad_mode(value: str | None = None) -> str:
    selected = (value if value is not None else os.getenv("GIGAAM_VAD", "auto"))
    selected = selected.strip().lower()
    if selected == "auto":
        return "auto"
    if selected in {"1", "true", "yes", "on"}:
        return "always"
    if selected in {"0", "false", "no", "off"}:
        return "never"
    raise ValueError("GIGAAM_VAD must be auto, true, or false")


class Handler:
    def __init__(self, usecase: Usecase) -> None:
        self.usecase = usecase

    def execute(self) -> Result:
        auto_vad_seconds = float(os.getenv("GIGAAM_AUTO_VAD_SECONDS", "20"))
        if not 0 < auto_vad_seconds <= 20:
            raise ValueError("GIGAAM_AUTO_VAD_SECONDS must be between 0 and 20")
        return self.usecase.execute(
            Input(
                input_path=Path(os.getenv("INPUT_PATH", "/data/input")),
                vad_mode=vad_mode(),
                auto_vad_seconds=auto_vad_seconds,
            )
        )


__all__ = ["Handler", "vad_mode"]
