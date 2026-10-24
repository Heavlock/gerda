from __future__ import annotations

import unittest
from unittest.mock import Mock

from assistant.operations.transcribe_russian_dictation.entity import Input, Result
from assistant.operations.transcribe_russian_dictation.presentation.cli import Handler


class CLITests(unittest.TestCase):
    def test_printable_result_comes_from_one_usecase_call(self) -> None:
        usecase = Mock()
        usecase.execute.return_value = Result('Русский текст.')
        self.assertEqual(Handler(usecase).execute('prompt'), 'Русский текст.')
        usecase.execute.assert_called_once_with(Input('prompt'))

    def test_invalid_token_is_rejected_before_usecase(self) -> None:
        usecase = Mock()
        with self.assertRaises(ValueError):
            Handler(usecase).execute('../../prompt')
        usecase.execute.assert_not_called()
