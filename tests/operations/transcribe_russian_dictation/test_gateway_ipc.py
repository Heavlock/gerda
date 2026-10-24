from __future__ import annotations

from pathlib import Path
import unittest
from unittest.mock import patch

from assistant.operations.transcribe_russian_dictation.entity import Input, RecognitionError
from assistant.operations.transcribe_russian_dictation.gateway.ipc import RemoteUsecase


class RemoteTests(unittest.TestCase):
    def test_connect_retry_waits_for_cold_worker_without_resubmitting_a_request(self) -> None:
        with patch('assistant.operations.transcribe_russian_dictation.gateway.ipc.subprocess.run') as start, \
             patch('assistant.operations.transcribe_russian_dictation.gateway.ipc.request') as request, \
             patch('assistant.operations.transcribe_russian_dictation.gateway.ipc.time.sleep'):
            request.side_effect = [FileNotFoundError(), {'text': 'Привет.'}]
            result = RemoteUsecase(Path('/tmp/control.sock')).execute(Input('prompt'))
            self.assertEqual(result.text, 'Привет.')
            self.assertEqual(request.call_count, 2)
            self.assertEqual(start.call_count, 2)

    def test_inference_timeout_never_resubmits_audio(self) -> None:
        with patch('assistant.operations.transcribe_russian_dictation.gateway.ipc.subprocess.run'), \
             patch('assistant.operations.transcribe_russian_dictation.gateway.ipc.request') as request:
            request.side_effect = TimeoutError()
            with self.assertRaises(RecognitionError):
                RemoteUsecase(Path('/tmp/control.sock')).execute(Input('prompt'))
            request.assert_called_once()

    def test_expected_server_error_is_returned_to_the_caller(self) -> None:
        with patch('assistant.operations.transcribe_russian_dictation.gateway.ipc.subprocess.run'), \
             patch('assistant.operations.transcribe_russian_dictation.gateway.ipc.request', return_value={'error': 'Повреждённая запись'}):
            with self.assertRaisesRegex(RecognitionError, 'Повреждённая запись'):
                RemoteUsecase(Path('/tmp/control.sock')).execute(Input('prompt'))

    def test_unexpected_or_oversized_server_result_is_rejected(self) -> None:
        for reply in [{'text': 1}, {'text': 'a' * 16001}, {'status': 'error'}]:
            with self.subTest(reply=str(reply)[:50]), \
                 patch('assistant.operations.transcribe_russian_dictation.gateway.ipc.subprocess.run'), \
                 patch('assistant.operations.transcribe_russian_dictation.gateway.ipc.request', return_value=reply), \
                 self.assertRaises(RecognitionError):
                RemoteUsecase(Path('/tmp/control.sock')).execute(Input('prompt'))
