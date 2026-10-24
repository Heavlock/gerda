from __future__ import annotations

from app.operations.transcribe_media.entity import Input, Result, SegmentData
from app.operations.transcribe_media.interface import (
    MediaGateway,
    ProgressGateway,
    Repository,
    TranscriberGateway,
)


class TranscribeMedia:
    def __init__(
        self,
        media: MediaGateway,
        transcriber: TranscriberGateway,
        repository: Repository,
        progress: ProgressGateway,
    ) -> None:
        self.media = media
        self.transcriber = transcriber
        self.repository = repository
        self.progress = progress

    def execute(self, input_data: Input) -> Result:
        sources = self.media.discover(input_data.input_path)
        if not sources:
            raise ValueError(f"No supported media files found in {input_data.input_path}")

        processed: list[Path] = []
        for source in sources:
            self.progress.report(f"Transcribing {source.name}")
            with self.media.prepare_audio(source) as audio_path:
                duration = self.media.duration(audio_path)
                use_vad = input_data.vad_mode == "always" or (
                    input_data.vad_mode == "auto"
                    and duration > input_data.auto_vad_seconds
                )
                if use_vad:
                    self.progress.report(
                        f"Using Silero VAD for {duration:.2f}s audio"
                    )
                    segments = self.transcriber.recognize_with_vad(audio_path)
                else:
                    self.progress.report(
                        f"Using direct GigaAM for {duration:.2f}s audio"
                    )
                    text = self.transcriber.recognize_direct(audio_path)
                    segments = (
                        [SegmentData(id=0, start=0.0, end=duration, text=text)]
                        if text
                        else []
                    )
            self.repository.save(source, duration, segments)
            processed.append(source)
            self.progress.report(f"Saved outputs for {source.name}")
        return Result(processed_files=tuple(processed))


__all__ = ["TranscribeMedia"]
