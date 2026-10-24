"""CLI composition root for the transcribe-media operation."""

from __future__ import annotations

import os
from pathlib import Path

from app.operations.transcribe_media.entity import SegmentData
from app.operations.transcribe_media.gateway.console import ProgressGateway
from app.operations.transcribe_media.gateway.ffmpeg import (
    SUPPORTED_EXTENSIONS,
    MediaGateway,
    discover_inputs,
    extract_audio,
    wav_duration,
)
from app.operations.transcribe_media.gateway.gigaam import (
    MODEL_NAME,
    TranscriberGateway,
)
from app.operations.transcribe_media.presentation.cli import Handler, vad_mode
from app.operations.transcribe_media.repository.filesystem import (
    OutputRepository,
    format_srt_timestamp,
    write_outputs,
)
from app.operations.transcribe_media.usecase import TranscribeMedia


def main() -> None:
    output_dir = Path(os.getenv("OUTPUT_DIR", "/data/output"))
    model_dir = Path(os.getenv("GIGAAM_MODEL_DIR", "/models/gigaam-v3-e2e-rnnt"))
    vad_model_dir = Path(os.getenv("GIGAAM_VAD_MODEL_DIR", "/models/silero-vad"))
    vad_batch_size = int(os.getenv("GIGAAM_VAD_BATCH_SIZE", "4"))
    max_speech_duration = float(os.getenv("GIGAAM_MAX_SPEECH_SECONDS", "20"))
    min_silence_duration = float(
        os.getenv("GIGAAM_MIN_SILENCE_MILLISECONDS", "500")
    )

    if not model_dir.is_dir():
        raise FileNotFoundError(
            f"GigaAM model directory does not exist: {model_dir}"
        )
    if vad_batch_size < 1:
        raise ValueError("GIGAAM_VAD_BATCH_SIZE must be positive")
    if not 0 < max_speech_duration <= 20:
        raise ValueError("GIGAAM_MAX_SPEECH_SECONDS must be between 0 and 20")
    if min_silence_duration < 0:
        raise ValueError("GIGAAM_MIN_SILENCE_MILLISECONDS must not be negative")

    progress = ProgressGateway()
    progress.report(f"Loading {MODEL_NAME} INT8 from {model_dir}")
    usecase = TranscribeMedia(
        MediaGateway(),
        TranscriberGateway(
            model_dir,
            vad_model_dir,
            vad_batch_size=vad_batch_size,
            max_speech_duration=max_speech_duration,
            min_silence_duration=min_silence_duration,
        ),
        OutputRepository(output_dir),
        progress,
    )
    try:
        Handler(usecase).execute()
    except ValueError as error:
        if str(error).startswith("No supported media files found"):
            raise SystemExit(
                f"{error}. Supported extensions: "
                f"{', '.join(sorted(SUPPORTED_EXTENSIONS))}"
            ) from error
        raise


__all__ = [
    "MODEL_NAME",
    "SUPPORTED_EXTENSIONS",
    "SegmentData",
    "discover_inputs",
    "extract_audio",
    "format_srt_timestamp",
    "main",
    "vad_mode",
    "wav_duration",
    "write_outputs",
]


if __name__ == "__main__":
    main()
