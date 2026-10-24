from __future__ import annotations

import logging
from pathlib import Path
import re
import threading
import wave

from ...entity import RecognitionError


class GigaamRecognizer:
    def __init__(self, model: Path, vad: Path, recordings: Path, *, threads: int = 2) -> None:
        self.model_path = model
        self.vad_path = vad
        self.recordings = recordings
        self.threads = threads
        self.model = None
        self.vad_model = None
        self.lock = threading.RLock()

    def _path(self, capture: str) -> Path:
        if not re.fullmatch(r'[A-Za-z0-9_-]{1,64}', capture):
            raise RecognitionError('Некорректная запись')
        path = self.recordings / (capture + '.wav')
        if path.is_symlink():
            raise RecognitionError('Некорректный путь записи')
        return path

    def duration(self, capture: str) -> float:
        try:
            path = self._path(capture)
            if path.stat().st_size > 128 * 1024 * 1024:
                raise RecognitionError('Запись слишком большая')
            with wave.open(str(path), 'rb') as audio:
                if (audio.getnchannels(), audio.getframerate(), audio.getsampwidth(), audio.getcomptype()) != (1, 16000, 2, 'NONE'):
                    raise RecognitionError('Ожидается моно WAV PCM16 с частотой 16000 Гц')
                return audio.getnframes() / audio.getframerate()
        except (OSError, wave.Error, EOFError) as error:
            raise RecognitionError('Аудиозапись недоступна или повреждена') from error

    def _options(self):
        import onnxruntime
        options = onnxruntime.SessionOptions()
        options.intra_op_num_threads = self.threads
        options.inter_op_num_threads = 1
        return options

    def load(self) -> None:
        with self.lock:
            if self.model is not None:
                return
            import onnx_asr
            self.model = onnx_asr.load_model(
                'gigaam-v3-e2e-rnnt', str(self.model_path), quantization='int8',
                providers=['CPUExecutionProvider'], sess_options=self._options())
            logging.info('Russian GigaAM ready: device=cpu compute_type=int8 threads=%s', self.threads)

    def recognize(self, capture: str, *, with_vad: bool) -> str:
        with self.lock:
            try:
                self.load()
                path = str(self._path(capture))
                if not with_vad:
                    return self.model.recognize(path).strip()
                if self.vad_model is None:
                    import onnx_asr
                    vad = onnx_asr.load_vad('silero', str(self.vad_path),
                                           providers=['CPUExecutionProvider'], sess_options=self._options())
                    self.vad_model = self.model.with_vad(vad, batch_size=4,
                                                        max_speech_duration_s=20,
                                                        min_silence_duration_ms=500)
                return ' '.join(segment.text.strip() for segment in self.vad_model.recognize(path)
                                if segment.text.strip())
            except RecognitionError:
                raise
            except Exception as error:
                raise RecognitionError('Ошибка русского распознавания; запись не вставлена') from error
