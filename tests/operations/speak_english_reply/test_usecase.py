from __future__ import annotations
import unittest
from unittest.mock import Mock
from assistant.operations.speak_english_reply.entity import Input
from assistant.operations.speak_english_reply.usecase import SpeakEnglishReply, spoken_text


class SpeechTests(unittest.TestCase):
    def test_filters_code_links_paths_and_preserves_english(self):
        text='## Result\nThe change works.\n```python\nprint("secret code")\n```\nSee [details](https://example.org) and `/home/user/project/file.py`.'
        result=spoken_text(text)
        self.assertIn('The change works.',result)
        self.assertIn('details',result)
        self.assertNotIn('secret code',result)
        self.assertNotIn('/home/',result)
        self.assertNotIn('https://',result)

    def test_unclosed_code_fence_is_not_read_as_english(self):
        self.assertNotIn('print',spoken_text('Explanation.\n```python\nprint(42)'))

    def test_replaced_pane_never_queues_speech(self):
        pane,speech=Mock(),Mock();pane.matches.return_value=False
        result=SpeakEnglishReply(pane,speech).execute(Input('p','/s','t','s','turn','Hello world.'))
        self.assertEqual(result.status,'unavailable');speech.submit.assert_not_called()

    def test_reply_identity_is_forwarded_to_voice_queue(self):
        pane,speech=Mock(),Mock();pane.matches.return_value=True
        result=SpeakEnglishReply(pane,speech).execute(Input('p','/s','t','s','turn','Hello world.'))
        self.assertEqual(result.status,'queued')
        speech.submit.assert_called_once_with('p','/s','t','s','turn','Hello world.')

    def test_russian_answer_is_not_mispronounced_by_english_only_model(self):
        pane,speech=Mock(),Mock();pane.matches.return_value=True
        result=SpeakEnglishReply(pane,speech).execute(Input('p','/s','t','s','turn','Это ответ на русском языке.'))
        self.assertEqual(result.status,'language');speech.submit.assert_not_called()
