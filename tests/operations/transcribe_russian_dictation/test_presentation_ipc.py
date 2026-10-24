from __future__ import annotations

import unittest
from unittest.mock import Mock

from assistant.operations.transcribe_russian_dictation.entity import Input, RecognitionError, Result
from assistant.operations.transcribe_russian_dictation.presentation.ipc import Handler


class IPCTests(unittest.TestCase):
    def test_valid_token_calls_usecase_once(self) -> None:
        usecase = Mock()
        usecase.execute.return_value = Result('Привет.')
        self.assertEqual(Handler(usecase).execute({'capture': 'prompt'}), {'text': 'Привет.'})
        usecase.execute.assert_called_once_with(Input('prompt'))

    def test_arbitrary_paths_and_extra_fields_never_reach_usecase(self) -> None:
        usecase = Mock()
        for body in [{}, {'capture': '../prompt'}, {'capture': '/tmp/prompt'},
                     {'capture': ''}, {'capture': 4}, {'capture': 'x' * 65},
                     {'capture': 'prompt', 'command': 'shell'}]:
            with self.subTest(body=body), self.assertRaises(ValueError):
                Handler(usecase).execute(body)
        usecase.execute.assert_not_called()

    def test_expected_error_is_presented_without_text(self) -> None:
        usecase = Mock()
        usecase.execute.side_effect = RecognitionError('Запись повреждена')
        self.assertEqual(Handler(usecase).execute({'capture': 'prompt'}), {'error': 'Запись повреждена'})
