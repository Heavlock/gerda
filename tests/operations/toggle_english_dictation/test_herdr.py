from pathlib import Path
import json
import subprocess
import tempfile
import unittest
from unittest.mock import patch, Mock
from assistant.operations.toggle_english_dictation.gateway.herdr import HerdrGateway
from assistant.operations.toggle_english_dictation.entity import VoiceError
from assistant.operations.speak_english_reply.gateway.emma import PaneGateway


class HerdrProtocolTests(unittest.TestCase):
    def test_literal_insert_ack_is_exit_status_not_json(self):
        gateway=HerdrGateway(Path('/bin/herdr'))
        with patch('subprocess.run',return_value=subprocess.CompletedProcess([],0,stdout='',stderr='')):
            self.assertEqual(gateway._call('w1:p2','/tmp/herdr.sock',['pane','send-text','w1:p2','text'],expect_json=False),'')

    def test_metadata_never_succeeds_without_structured_pane_identity(self):
        gateway=HerdrGateway(Path('/bin/herdr'))
        with patch('subprocess.run',return_value=subprocess.CompletedProcess([],0,stdout='',stderr='')):
            with self.assertRaises(VoiceError):gateway.inspect('w1:p2','/tmp/herdr.sock')


class SessionResolutionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.history = Path(self.temp.name) / 'history.jsonl'
        self.history.write_text(json.dumps({'session_id':'abc','ts':100,
            'text':"Hey, how are you?\n\nPlease reply in English."}) + '\n')
        self.gateway = HerdrGateway(Path('/bin/herdr'), self.history)
        self.rendered = ('› Hey, how are you?\n\n  Please reply in English.\n\n'
                         '• Hello!\n\n› Ask Codex to do anything\n\n  GPT · ~/project\n')

    def inspect(self, reported=None):
        pane = {'pane_id':'w1:p4','terminal_id':'terminal','agent':'codex'}
        if reported:
            pane['agent_session'] = {'kind':'id','agent':'codex','value':reported}
        with patch.object(self.gateway, '_call', side_effect=[{'result':{'pane':pane}}, self.rendered]):
            return self.gateway.inspect('w1:p4','/tmp/herdr.sock')

    def test_new_pane_without_session_hook_resolves_from_its_committed_prompt(self):
        self.assertEqual(self.inspect().session, 'abc')

    def test_polling_uses_only_passive_detection_without_history_collection(self):
        pane = {'pane_id':'w1:p4','terminal_id':'terminal','agent':'codex'}
        with patch.object(self.gateway, '_call', side_effect=[{'result':{'pane':pane}}, self.rendered]) as call:
            self.gateway.inspect('w1:p4','/tmp/herdr.sock')
            args = call.call_args.args[2]
            self.assertEqual(args, ['pane','read','w1:p4','--source','detection'])

    def test_stale_hook_from_another_pane_cannot_override_visible_prompt(self):
        self.assertEqual(self.inspect('def').session, 'abc')

    def test_composer_is_never_treated_as_a_submitted_prompt(self):
        self.rendered = '› Hey, how are you?\n\n  Please reply in English.\n\n  GPT · ~/project\n'
        self.assertIsNone(self.inspect('def').session)

    def test_wrapped_prompt_and_blank_lines_match_exact_native_history_text(self):
        self.rendered = self.rendered.replace('Hey, how are you?', 'Hey, how\n  are you?')
        self.assertEqual(self.inspect().session, 'abc')

    def test_terminal_soft_wrap_inside_a_word_preserves_prompt_matching(self):
        self.rendered = self.rendered.replace('English.', 'Eng\n  lish.')
        self.assertEqual(self.inspect().session, 'abc')

    def saved_reply(self, text):
        path = self.history.parent/'sessions/2026/10/16/rollout-abc.jsonl'
        path.parent.mkdir(parents=True)
        path.write_text(json.dumps({'type':'session_meta','payload':{'id':'abc'}})+'\n'+
                        json.dumps({'type':'event_msg','payload':{'type':'task_complete',
                                    'turn_id':'turn','last_agent_message':text}})+'\n')
        return path

    def test_long_reply_reconfirms_known_session_without_scrolling_to_the_prompt(self):
        self.assertEqual(self.inspect().session, 'abc')
        text = 'This is the final English sentence of a long answer. ' * 5
        self.saved_reply(text)
        self.rendered = '• ' + text + '\n\n› Ask Codex to do anything\n'
        self.assertEqual(self.inspect().session, 'abc')

    def test_new_or_unrelated_screen_does_not_inherit_a_cached_session(self):
        self.inspect()
        self.saved_reply('The ending of the known answer is long enough to verify precisely. '*4)
        self.rendered = 'Welcome to Codex\n\n› Ask Codex to do anything\n'
        self.assertIsNone(self.inspect('abc').session)

    def test_old_visible_reply_cannot_confirm_a_new_unfinished_turn(self):
        self.inspect()
        text = 'This older completed English answer cannot identify a newer running turn. '*4
        path = self.saved_reply(text)
        with path.open('a') as stream:
            stream.write(json.dumps({'type':'event_msg','payload':{'type':'task_started','turn_id':'next'}})+'\n')
        self.rendered = '• '+text+'\n\n› Ask Codex to do anything\n'
        self.assertIsNone(self.inspect().session)

    def test_ambiguous_prompt_in_different_threads_is_rejected(self):
        with self.history.open('a') as stream:
            stream.write(json.dumps({'session_id':'def','text':'Hey, how are you? Please reply in English.'})+'\n')
        result = self.inspect()
        self.assertIsNone(result.session)
        self.assertIn('разных сессиях', result.session_error)

    def test_missing_history_preserves_pane_for_f7_and_reports_f6_binding_error(self):
        self.history.unlink()
        result = self.inspect()
        self.assertEqual(result.terminal, 'terminal')
        self.assertIsNone(result.session)
        self.assertIn('недоступна', result.session_error)

    def test_only_last_committed_prompt_can_authorize_current_session(self):
        self.rendered = self.rendered.replace('› Ask Codex', '› A different new request\n\n• Answer\n\n› Ask Codex')
        self.assertIsNone(self.inspect('abc').session)

    def test_speech_rechecks_the_resolved_session_and_terminal(self):
        lookup = Mock(return_value=('terminal','abc','codex'))
        speech_pane = PaneGateway(lookup)
        self.assertTrue(speech_pane.matches('w1:p4','/tmp/herdr.sock','terminal','abc'))
        self.assertFalse(speech_pane.matches('w1:p4','/tmp/herdr.sock','terminal','def'))
        lookup.return_value = ('replacement','abc','codex')
        self.assertFalse(speech_pane.matches('w1:p4','/tmp/herdr.sock','terminal','abc'))
        lookup.side_effect = VoiceError('unavailable')
        self.assertFalse(speech_pane.matches('w1:p4','/tmp/herdr.sock','terminal','abc'))
