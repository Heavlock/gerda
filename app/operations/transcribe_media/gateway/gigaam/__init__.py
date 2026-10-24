from __future__ import annotations

from pathlib import Path

import onnx_asr

from app.operations.transcribe_media.entity import SegmentData


MODEL_NAME = "gigaam-v3-e2e-rnnt"


class TranscriberGateway:
    def __init__(
        self,
        model_dir: Path,
        vad_model_dir: Path,
        *,
        vad_batch_size: int,
        max_speech_duration: float,
        min_silence_duration: float,
    ) -> None:
        self.model_dir = model_dir
        self.vad_model_dir = vad_model_dir
        self.vad_batch_size = vad_batch_size
        self.max_speech_duration = max_speech_duration
        self.min_silence_duration = min_silence_duration
        self.model = None
        self.vad_recognizer = None

    def recognize_direct(self, audio_path: Path) -> str:
        return self._model().recognize(str(audio_path)).strip()

    def recognize_with_vad(self, audio_path: Path) -> list[SegmentData]:
        if self.vad_recognizer is None:
            if not self.vad_model_dir.is_dir():
                raise FileNotFoundError(
                    f"Silero VAD model directory does not exist: {self.vad_model_dir}"
                )
            vad = onnx_asr.load_vad(
                "silero",
                str(self.vad_model_dir),
                providers=["CPUExecutionProvider"],
            )
            self.vad_recognizer = self._model().with_vad(
                vad,
                batch_size=self.vad_batch_size,
                max_speech_duration_s=self.max_speech_duration,
                min_silence_duration_ms=self.min_silence_duration,
            )
        return [
            SegmentData(
                id=index,
                start=result.start,
                end=result.end,
                text=result.text.strip(),
            )
            for index, result in enumerate(
                self.vad_recognizer.recognize(str(audio_path))
            )
            if result.text.strip()
        ]

    def _model(self):
        if self.model is None:
            if not self.model_dir.is_dir():
                raise FileNotFoundError(
                    f"GigaAM model directory does not exist: {self.model_dir}"
                )
            self.model = onnx_asr.load_model(
                MODEL_NAME,
                str(self.model_dir),
                quantization="int8",
                providers=["CPUExecutionProvider"],
            )
        return self.model


__all__ = ["MODEL_NAME", "TranscriberGateway"]
