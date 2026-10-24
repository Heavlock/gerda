from __future__ import annotations

import unittest
from unittest.mock import Mock

from assistant.operations.transcribe_russian_dictation.entity import Input, RecognitionError
from assistant.operations.transcribe_russian_dictation.usecase import TranscribeRussianDictation


class TranscribeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.recognizer = Mock()
        self.recognizer.duration.return_value = 5
        self.recognizer.recognize.return_value = '  Привет\n  мир. '
        self.usecase = TranscribeRussianDictation(self.recognizer)

    def test_short_recording_uses_direct_recognition_and_normalizes_text(self) -> None:
        self.assertEqual(self.usecase.execute(Input('prompt')).text, 'Привет мир.')
        self.recognizer.recognize.assert_called_once_with('prompt', with_vad=False)

    def test_only_recordings_above_twenty_seconds_use_vad(self) -> None:
        for duration, expected in [(0.1, False), (20, False), (20.001, True), (60, True)]:
            with self.subTest(duration=duration):
                self.recognizer.duration.return_value = duration
                self.usecase.execute(Input('prompt'))
                self.recognizer.recognize.assert_called_with('prompt', with_vad=expected)

    def test_too_short_recording_is_rejected_without_inference(self) -> None:
        self.recognizer.duration.return_value = 0.099
        with self.assertRaises(RecognitionError):
            self.usecase.execute(Input('prompt'))
        self.recognizer.recognize.assert_not_called()

    def test_silence_returns_empty_text(self) -> None:
        self.recognizer.recognize.return_value = ' \n '
        self.assertEqual(self.usecase.execute(Input('prompt')).text, '')

    def test_oversized_transcript_is_rejected(self) -> None:
        self.recognizer.recognize.return_value = 'я' * 16001
        with self.assertRaises(RecognitionError):
            self.usecase.execute(Input('prompt'))

    def test_recognition_error_is_not_retried(self) -> None:
        self.recognizer.recognize.side_effect = RecognitionError('failed')
        with self.assertRaises(RecognitionError):
            self.usecase.execute(Input('prompt'))
        self.recognizer.recognize.assert_called_once()
