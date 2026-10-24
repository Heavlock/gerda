from __future__ import annotations
import unittest
from unittest.mock import Mock
from assistant.operations.toggle_english_dictation.entity import Binding, Input, VoiceError
from assistant.operations.toggle_english_dictation.repository.memory import RecordingRepository
from assistant.operations.toggle_english_dictation.usecase import ToggleEnglishDictation
from assistant.operations.toggle_english_dictation.presentation.ipc import Handler


class ToggleTests(unittest.TestCase):
    def setUp(self):
        self.store = RecordingRepository()
        self.capture, self.asr, self.herdr, self.replies, self.speech = [Mock() for _ in range(5)]
        self.binding = Binding('w1:p2', '/tmp/herdr.sock', 'terminal-2', 'thread-1', 'codex')
        self.herdr.inspect.return_value = self.binding
        self.capture.start.return_value = 'capture1'
        self.asr.transcribe.return_value = 'Please explain this code.'
        self.replies.arm.return_value = 'registration'
        self.uc = ToggleEnglishDictation(self.store, self.capture, self.asr, self.herdr, self.replies, self.speech)

    def call(self, mode='dictate', pane='w1:p2'):
        return self.uc.execute(Input(mode, pane, '/tmp/herdr.sock'))

    def test_stopping_after_focus_change_inserts_into_saved_pane(self):
        self.assertEqual(self.call().status, 'recording')
        self.assertEqual(self.call(pane='w1:p9').status, 'inserted')
        self.herdr.inspect.assert_called_with('w1:p2', '/tmp/herdr.sock')
        self.herdr.insert.assert_called_once_with(self.binding, 'Please explain this code.')
        self.replies.arm.assert_not_called()
        self.capture.finish.assert_called_once_with('capture1')
        self.assertIsNone(self.store.get())

    def test_speaking_mode_arms_before_insert_and_commits_after_it(self):
        order = []
        self.replies.arm.side_effect = lambda *a: order.append('arm') or 'registration'
        self.herdr.insert.side_effect = lambda *a: order.append('insert')
        self.replies.commit.side_effect = lambda *a: order.append('commit')
        self.call('speak')
        self.assertEqual(self.call('speak').status, 'inserted')
        self.assertEqual(order, ['arm', 'insert', 'commit'])
        self.assertTrue(self.herdr.insert.call_args.args[1].endswith('Please reply in English.'))
        self.speech.prewarm.assert_called_once()

    def test_both_hotkeys_transcribe_only_after_recording_stops(self):
        for mode in ['dictate', 'speak']:
            with self.subTest(mode=mode):
                self.setUp()
                order = []
                self.capture.stop.side_effect = lambda *a: order.append('stop')
                self.asr.transcribe.side_effect = lambda *a: order.append('recognize') or 'Hello.'
                self.assertEqual(self.call(mode).status, 'recording')
                self.asr.transcribe.assert_not_called()
                self.assertEqual(self.call(mode).status, 'inserted')
                self.assertEqual(order, ['stop', 'recognize'])
                self.asr.transcribe.assert_called_once_with('capture1')

    def test_cross_mode_key_does_not_stop_or_move_capture(self):
        self.call('speak')
        self.assertEqual(self.call('dictate').status, 'busy')
        self.capture.stop.assert_not_called()
        self.assertEqual(self.store.get().mode, 'speak')

    def test_failed_insert_revokes_observer_and_cleans_audio(self):
        self.call('speak')
        self.herdr.insert.side_effect = VoiceError('failed')
        self.assertEqual(self.call('speak').status, 'error')
        self.replies.revoke.assert_called_once_with('registration')
        self.replies.commit.assert_not_called()
        self.capture.finish.assert_called_once()
        self.assertIsNone(self.store.get())

    def test_thread_replacement_rejects_before_insert(self):
        self.call('speak')
        self.herdr.inspect.return_value = Binding('w1:p2', '/tmp/herdr.sock', 'terminal-2', 'other', 'codex')
        self.assertEqual(self.call('speak').status, 'error')
        self.herdr.insert.assert_not_called()
        self.capture.finish.assert_called_once()

    def test_empty_or_failed_recognition_never_inserts_and_releases_capture(self):
        for result in ['', VoiceError('ASR unavailable')]:
            with self.subTest(result=result):
                self.setUp()
                self.call()
                if isinstance(result, Exception):
                    self.asr.transcribe.side_effect = result
                else:
                    self.asr.transcribe.return_value = result
                self.assertIn(self.call().status, ['empty', 'error'])
                self.herdr.insert.assert_not_called()
                self.capture.finish.assert_called_once()
                self.assertIsNone(self.store.get())

    def test_plain_terminal_allows_f7_but_rejects_f6(self):
        self.herdr.inspect.return_value = Binding('w1:p2', '/tmp/herdr.sock', 'terminal-2', None, None)
        self.assertEqual(self.call('speak').status, 'error')
        self.capture.start.assert_not_called()
        self.assertEqual(self.call().status, 'recording')

    def test_uncertain_session_rejects_f6_but_keeps_f7_insertion_working(self):
        self.herdr.inspect.return_value = Binding('w1:p2', '/tmp/herdr.sock', 'terminal-2',
                                                 None, 'codex', 'Ambiguous session')
        self.assertEqual(self.call('speak').status, 'error')
        self.capture.start.assert_not_called()
        self.assertEqual(self.call().status, 'recording')
        self.assertEqual(self.call().status, 'inserted')
        self.replies.arm.assert_not_called()

    def test_uncertain_session_after_recording_releases_capture_without_arming(self):
        self.call('speak')
        self.herdr.inspect.return_value = Binding('w1:p2', '/tmp/herdr.sock', 'terminal-2',
                                                 None, 'codex', 'Ambiguous session')
        self.assertEqual(self.call('speak').status, 'error')
        self.replies.arm.assert_not_called()
        self.capture.finish.assert_called_once()
        self.assertIsNone(self.store.get())

    def test_capture_failure_keeps_state_empty(self):
        self.capture.start.side_effect = VoiceError('busy microphone')
        self.assertEqual(self.call().status, 'error')
        self.assertIsNone(self.store.get())

    def test_f7_disarms_same_panel_before_stopping_playback(self):
        order = []
        self.replies.cancel.side_effect = lambda *a: order.append('disarm')
        self.speech.cancel.side_effect = lambda: order.append('stop-playback')
        self.capture.start.side_effect = lambda: order.append('record') or 'capture1'
        self.call()
        self.assertEqual(order, ['disarm', 'stop-playback', 'record'])

    def test_parallel_hotkey_is_rejected_without_capture(self):
        self.store.acquire()
        try:
            self.assertEqual(self.call().status, 'busy')
            self.capture.start.assert_not_called()
        finally:
            self.store.release()

    def test_presentation_rejects_invalid_modes_and_extra_fields(self):
        handler = Handler(Mock())
        for payload in [{'mode':'other','pane':'w1:p2','socket':'/tmp/herdr.sock'},
                        {'mode':'dictate','pane':'w1:p2','socket':'/tmp/herdr.sock','command':'shell'},
                        {'mode':'dictate','pane':'','socket':'/tmp/herdr.sock'}]:
            with self.assertRaises(ValueError):
                handler.execute(payload)
        handler.usecase.execute.assert_not_called()
