from __future__ import annotations

from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
import wave

from assistant.operations.transcribe_russian_dictation.entity import RecognitionError
from assistant.operations.transcribe_russian_dictation.gateway.gigaam import GigaamRecognizer


class GigaamTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name)
        self.recognizer = GigaamRecognizer(Path('model'), Path('vad'), self.directory)
        self.model = Mock()
        self.model.recognize.return_value = 'Привет.'
        self.vad = Mock()
        self.model.with_vad.return_value.recognize.side_effect = lambda *a: iter([
            SimpleNamespace(text=' Первый. '), SimpleNamespace(text=' '), SimpleNamespace(text='Второй.')])
        self.loader = Mock(return_value=self.model)
        self.vad_loader = Mock(return_value=self.vad)
        modules = {
            'onnx_asr': SimpleNamespace(load_model=self.loader, load_vad=self.vad_loader),
            'onnxruntime': SimpleNamespace(SessionOptions=SimpleNamespace),
        }
        patcher = patch.dict('sys.modules', modules)
        patcher.start()
        self.addCleanup(patcher.stop)

    def write_audio(self, *, rate: int = 16000, channels: int = 1, width: int = 2) -> Path:
        path = self.directory / 'prompt.wav'
        with wave.open(str(path), 'wb') as audio:
            audio.setnchannels(channels)
            audio.setsampwidth(width)
            audio.setframerate(rate)
            audio.writeframes(b'\0' * rate * channels * width)
        return path

    def test_capture_format_and_duration_are_checked(self) -> None:
        self.write_audio()
        self.assertEqual(self.recognizer.duration('prompt'), 1)
        for options in [{'rate': 8000}, {'channels': 2}, {'width': 1}]:
            self.write_audio(**options)
            with self.assertRaises(RecognitionError):
                self.recognizer.duration('prompt')

    def test_missing_corrupt_symlink_and_traversal_inputs_are_rejected(self) -> None:
        with self.assertRaises(RecognitionError):
            self.recognizer.duration('missing')
        (self.directory / 'prompt.wav').write_bytes(b'invalid')
        with self.assertRaises(RecognitionError):
            self.recognizer.duration('prompt')
        (self.directory / 'link.wav').symlink_to(self.directory / 'prompt.wav')
        for name in ['link', '../prompt', '/tmp/prompt']:
            with self.assertRaises(RecognitionError):
                self.recognizer.duration(name)

    def test_repeated_requests_reuse_int8_model_and_bounded_session_threads(self) -> None:
        self.recognizer.load()
        self.assertEqual(self.recognizer.recognize('prompt', with_vad=False), 'Привет.')
        self.assertEqual(self.recognizer.recognize('prompt', with_vad=False), 'Привет.')
        self.loader.assert_called_once()
        options = self.loader.call_args.kwargs
        self.assertEqual(options['quantization'], 'int8')
        self.assertEqual(options['providers'], ['CPUExecutionProvider'])
        self.assertEqual(options['sess_options'].intra_op_num_threads, 2)
        self.assertEqual(options['sess_options'].inter_op_num_threads, 1)
        self.vad_loader.assert_not_called()

    def test_long_requests_reuse_vad_and_preserve_segment_text(self) -> None:
        for _ in range(2):
            self.assertEqual(self.recognizer.recognize('prompt', with_vad=True), 'Первый. Второй.')
        self.loader.assert_called_once()
        self.vad_loader.assert_called_once()
        self.model.with_vad.assert_called_once_with(self.vad, batch_size=4,
                                                   max_speech_duration_s=20,
                                                   min_silence_duration_ms=500)

    def test_inference_failure_is_typed_and_next_request_can_succeed(self) -> None:
        self.model.recognize.side_effect = [RuntimeError('failed'), 'Успех.']
        with self.assertRaises(RecognitionError):
            self.recognizer.recognize('prompt', with_vad=False)
        self.assertEqual(self.recognizer.recognize('prompt', with_vad=False), 'Успех.')
        self.loader.assert_called_once()
