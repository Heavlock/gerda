from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from assistant.operations.toggle_english_dictation.entity import VoiceError
from assistant.operations.toggle_english_dictation.gateway.whisper import WhisperRecognizer


class WhisperTests(unittest.TestCase):
    def setUp(self) -> None:
        self.cpu = self.make_model('int8_float32', 'CPU transcript')
        self.gpu = self.make_model('int8_float16', 'GPU transcript')
        self.factory = Mock(side_effect=lambda *a, **kw: self.gpu if kw['device'] == 'cuda' else self.cpu)
        self.cuda_count = Mock(return_value=1)
        self.torch_cuda = Mock(return_value=True)
        modules = {
            'ctranslate2': SimpleNamespace(get_cuda_device_count=self.cuda_count),
            'torch': SimpleNamespace(cuda=SimpleNamespace(is_available=self.torch_cuda)),
            'faster_whisper': SimpleNamespace(WhisperModel=self.factory),
        }
        self.modules = patch.dict('sys.modules', modules)
        self.modules.start()
        self.addCleanup(self.modules.stop)
        self.recognizer = WhisperRecognizer(Path('local-model'), lambda capture: Path(capture + '.wav'))

    @staticmethod
    def make_model(precision: str, text: str) -> Mock:
        model = Mock()
        model.model.compute_type = precision
        model.transcribe.side_effect = lambda *a, **kw: (iter([SimpleNamespace(text=text)]), None)
        return model

    def devices(self) -> list[str]:
        return [call.kwargs['device'] for call in self.factory.call_args_list]

    def test_cuda_transcribes_with_existing_options_and_reuses_model(self) -> None:
        self.assertEqual(self.recognizer.transcribe('first'), 'GPU transcript')
        self.assertEqual(self.recognizer.transcribe('second'), 'GPU transcript')
        self.assertEqual(self.devices(), ['cuda'])
        self.factory.assert_called_once_with('local-model', device='cuda', compute_type='int8_float16',
                                             cpu_threads=2, num_workers=1, local_files_only=True)
        options = self.gpu.transcribe.call_args.kwargs
        self.assertEqual(self.gpu.transcribe.call_args.args, ('second.wav',))
        self.assertEqual(options['language'], 'en')
        self.assertEqual(options['task'], 'transcribe')
        self.assertEqual(options['beam_size'], 5)
        self.assertFalse(options['vad_filter'])
        self.assertFalse(options['condition_on_previous_text'])
        self.assertIn('PostgreSQL', options['initial_prompt'])

    def test_no_gpu_uses_cpu_and_does_not_probe_torch(self) -> None:
        self.cuda_count.return_value = 0
        with self.assertLogs(level='WARNING'):
            self.assertEqual(self.recognizer.transcribe('capture'), 'CPU transcript')
        self.torch_cuda.assert_not_called()
        self.factory.assert_called_once_with('local-model', device='cpu', compute_type='int8',
                                             cpu_threads=2, num_workers=1, local_files_only=True)

    def test_unavailable_torch_cuda_uses_cpu(self) -> None:
        self.torch_cuda.return_value = False
        with self.assertLogs(level='WARNING'):
            self.assertEqual(self.recognizer.transcribe('capture'), 'CPU transcript')
        self.assertEqual(self.devices(), ['cpu'])

    def test_cuda_probe_failure_uses_cpu(self) -> None:
        self.cuda_count.side_effect = RuntimeError('driver unavailable')
        with self.assertLogs(level='WARNING'):
            self.assertEqual(self.recognizer.transcribe('capture'), 'CPU transcript')
        self.assertEqual(self.devices(), ['cpu'])

    def test_missing_cuda_runtime_dependency_uses_cpu(self) -> None:
        with patch.dict('sys.modules', {'torch': None}), self.assertLogs(level='WARNING'):
            self.assertEqual(self.recognizer.transcribe('capture'), 'CPU transcript')
        self.assertEqual(self.devices(), ['cpu'])

    def test_failed_gpu_load_uses_cpu_without_repeated_gpu_attempts(self) -> None:
        self.factory.side_effect = [RuntimeError('CUDA out of memory'), self.cpu]
        with self.assertLogs(level='WARNING'):
            self.assertEqual(self.recognizer.transcribe('first'), 'CPU transcript')
        self.assertEqual(self.recognizer.transcribe('second'), 'CPU transcript')
        self.assertEqual(self.devices(), ['cuda', 'cpu'])

    def test_lazy_gpu_failure_discards_partial_text_and_retries_whole_recording(self) -> None:
        def broken_segments():
            yield SimpleNamespace(text='Partial GPU text must not be inserted')
            raise RuntimeError('CUDA out of memory')

        self.gpu.transcribe.side_effect = lambda *a, **kw: (broken_segments(), None)
        with self.assertLogs(level='WARNING'):
            self.assertEqual(self.recognizer.transcribe('first'), 'CPU transcript')
        self.gpu.model.unload_model.assert_called_once_with()
        self.assertEqual(self.cpu.transcribe.call_args.args, ('first.wav',))
        self.assertEqual(self.recognizer.transcribe('second'), 'CPU transcript')
        self.assertEqual(self.devices(), ['cuda', 'cpu'])
        self.assertEqual(self.gpu.transcribe.call_count, 1)

    def test_cpu_failure_returns_voice_error_without_retry_loop(self) -> None:
        self.cuda_count.return_value = 0
        failure = RuntimeError('CPU inference failed')
        self.cpu.transcribe.side_effect = failure
        with self.assertLogs(level='WARNING'), self.assertRaises(VoiceError) as caught:
            self.recognizer.transcribe('capture')
        self.assertIs(caught.exception.__cause__, failure)
        self.assertEqual(self.devices(), ['cpu'])
        self.cpu.transcribe.assert_called_once()

    def test_failed_cpu_retry_returns_voice_error(self) -> None:
        self.gpu.transcribe.side_effect = RuntimeError('CUDA failed')
        self.cpu.transcribe.side_effect = RuntimeError('CPU failed too')
        with self.assertLogs(level='WARNING'), self.assertRaises(VoiceError):
            self.recognizer.transcribe('capture')
        self.assertEqual(self.devices(), ['cuda', 'cpu'])
        self.cpu.transcribe.assert_called_once()

    def test_missing_recording_is_not_retried_on_cpu(self) -> None:
        self.gpu.transcribe.side_effect = FileNotFoundError('missing.wav')
        with self.assertRaises(VoiceError):
            self.recognizer.transcribe('missing')
        self.assertEqual(self.devices(), ['cuda'])

    def test_empty_recording_returns_empty_text(self) -> None:
        self.gpu.transcribe.side_effect = lambda *a, **kw: (iter([]), None)
        self.assertEqual(self.recognizer.transcribe('silence'), '')


if __name__ == '__main__':
    unittest.main()
