from __future__ import annotations
import logging
from pathlib import Path
import threading
from typing import Callable
from ...entity import VoiceError


class WhisperRecognizer:
    def __init__(self, model: Path, audio_path: Callable[[str], Path]) -> None:
        self.model_path = model
        self.audio_path = audio_path
        self.model = None
        self.device: str | None = None
        self.lock = threading.RLock()

    def load(self) -> None:
        with self.lock:
            if self.model is not None:
                return
            try:
                import ctranslate2
                if ctranslate2.get_cuda_device_count() > 0:
                    # The English environment already includes CUDA-enabled PyTorch
                    # for Emma. Import it to load its bundled cuBLAS/cuDNN libraries
                    # before CTranslate2 uses them (including direct CLI checks).
                    import torch
                    if torch.cuda.is_available():
                        self._load_model('cuda')
                        return
            except (ImportError, OSError, RuntimeError, ValueError):
                logging.warning('Whisper CUDA initialization failed; using CPU', exc_info=True)
            else:
                logging.warning('Whisper CUDA unavailable; using CPU')
            self._load_model('cpu')

    def _load_model(self, device: str) -> None:
        from faster_whisper import WhisperModel
        compute_type = 'int8_float16' if device == 'cuda' else 'int8'
        self.model = WhisperModel(str(self.model_path), device=device, compute_type=compute_type,
                                  cpu_threads=2, num_workers=1, local_files_only=True)
        self.device = device
        logging.info('Whisper ready: device=%s compute_type=%s threads=2', device,
                     self.model.model.compute_type)

    def _transcribe(self, path: Path) -> str:
        segments, _ = self.model.transcribe(
            str(path), language='en', task='transcribe',
            beam_size=5, vad_filter=False, condition_on_previous_text=False,
            initial_prompt='Software development glossary: PostgreSQL, SQLite, Git, Codex, API, authentication, authorization.')
        # Inference is lazy: consume every segment inside the fallback boundary.
        return ' '.join(s.text.strip() for s in segments).strip()

    def transcribe(self, capture: str) -> str:
        with self.lock:
            try:
                self.load()
                path = self.audio_path(capture)
                try:
                    return self._transcribe(path)
                except RuntimeError:
                    if self.device != 'cuda':
                        raise
                    logging.warning('Whisper CUDA inference failed; retrying recording on CPU',
                                    exc_info=True)
                    self.model.model.unload_model()
                    self.model = None
                    self.device = None
                    self._load_model('cpu')
                    return self._transcribe(path)
            except Exception as error:
                raise VoiceError('Ошибка английского распознавания; запись не вставлена') from error
