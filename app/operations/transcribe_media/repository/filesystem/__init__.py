from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from app.operations.transcribe_media.entity import SegmentData
from app.operations.transcribe_media.gateway.gigaam import MODEL_NAME


def format_srt_timestamp(seconds: float) -> str:
    total_ms = round(seconds * 1000)
    hours, remainder = divmod(total_ms, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    secs, milliseconds = divmod(remainder, 1000)
    return f"{hours:02}:{minutes:02}:{secs:02},{milliseconds:03}"


class OutputRepository:
    def __init__(self, output_dir: Path) -> None:
        self.output_dir = output_dir

    def save(
        self,
        source_file: Path,
        duration: float,
        segments: list[SegmentData],
    ) -> None:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        base = self.output_dir / source_file.stem

        txt_content = "\n".join(segment.text for segment in segments)
        base.with_suffix(".txt").write_text(
            txt_content + ("\n" if txt_content else ""),
            encoding="utf-8",
        )

        srt_parts: list[str] = []
        for index, segment in enumerate(segments, start=1):
            srt_parts.extend(
                (
                    str(index),
                    f"{format_srt_timestamp(segment.start)} --> "
                    f"{format_srt_timestamp(segment.end)}",
                    segment.text,
                    "",
                )
            )
        base.with_suffix(".srt").write_text(
            "\n".join(srt_parts),
            encoding="utf-8",
        )

        payload = {
            "source": source_file.name,
            "engine": MODEL_NAME,
            "language": "ru",
            "language_probability": None,
            "duration_seconds": duration,
            "duration_after_vad_seconds": sum(
                segment.end - segment.start for segment in segments
            ),
            "segments": [asdict(segment) for segment in segments],
        }
        base.with_suffix(".json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )


def write_outputs(
    output_dir: Path,
    source_file: Path,
    duration: float,
    segments: list[SegmentData],
) -> None:
    OutputRepository(output_dir).save(source_file, duration, segments)


__all__ = ["OutputRepository", "format_srt_timestamp", "write_outputs"]
