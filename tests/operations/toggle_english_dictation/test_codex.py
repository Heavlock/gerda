from __future__ import annotations
import json
from datetime import datetime, timezone
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import Mock
from assistant.operations.toggle_english_dictation.entity import Binding
from assistant.operations.toggle_english_dictation.gateway.codex import CodexReplies
from assistant.operations.toggle_english_dictation.gateway.codex.transcript import NextTurn, Tail, find_rollout


def user(turn='new', text='Edited English text'):
    return {'timestamp':datetime.now(timezone.utc).isoformat(),'type':'response_item','metadata':{'retained_source':{'id':{'turn_id':turn}}},
            'payload':{'type':'message','role':'user','content':[{'type':'input_text','text':text}]}}


def complete(turn='new', text='The English answer.'):
    return {'timestamp':datetime.now(timezone.utc).isoformat(),'type':'event_msg','payload':{'type':'task_complete','turn_id':turn,'last_agent_message':text}}


class TranscriptTests(unittest.TestCase):
    def test_old_completion_and_commentary_are_not_spoken(self):
        turn = NextTurn()
        self.assertIsNone(turn.feed(complete('old')))
        turn.feed(user())
        self.assertIsNone(turn.feed({'type':'response_item','payload':{'type':'message','role':'assistant',
            'phase':'commentary','turn_id':'new','content':[{'type':'output_text','text':'Working'}]}}))
        self.assertIsNone(turn.feed(complete('other')))
        self.assertEqual(turn.feed(complete()), 'The English answer.')
        self.assertIsNone(turn.feed(complete()))

    def test_abort_never_reads_a_later_or_previous_answer(self):
        turn = NextTurn()
        turn.feed(user())
        turn.feed({'type':'event_msg','payload':{'type':'turn_aborted','turn_id':'new'}})
        self.assertTrue(turn.aborted)
        self.assertIsNone(turn.feed(complete()))

    def test_final_without_task_text_uses_only_matching_final_phase(self):
        turn = NextTurn()
        turn.feed(user())
        turn.feed({'type':'response_item','payload':{'type':'message','role':'assistant','phase':'final_answer',
            'internal_chat_message_metadata_passthrough':{'turn_id':'new'},
            'content':[{'type':'output_text','text':'Final answer.'}]}})
        self.assertEqual(turn.feed(complete(text=None)), 'Final answer.')

    def test_tail_waits_for_partial_records_and_rejects_truncation(self):
        with tempfile.TemporaryDirectory() as temp:
            p = Path(temp)/'rollout.jsonl'
            p.write_text(json.dumps(user())[:-1])
            tail = Tail(p, 0)
            self.assertEqual(tail.read(), [])
            with p.open('a') as f:f.write('}\n')
            self.assertEqual(len(tail.read()), 1)
            p.write_text('')
            with self.assertRaises(ValueError):tail.read()

    def test_tail_discards_oversized_line_then_resumes(self):
        with tempfile.TemporaryDirectory() as temp:
            row = user()
            p = Path(temp)/'rollout.jsonl';p.write_text('x'*(1024*1024+30)+'\n'+json.dumps(row)+'\n')
            tail=Tail(p,0)
            self.assertEqual(tail.read(), [row])

    def test_rollout_identity_is_verified_not_guessed_from_filename(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);p=root/'2026/10/16/rollout-abc.jsonl';p.parent.mkdir(parents=True)
            p.write_text(json.dumps({'type':'session_meta','payload':{'id':'wrong'}})+'\n')
            with self.assertRaises(ValueError):find_rollout(root,'abc')
            p.write_text(json.dumps({'type':'session_meta','payload':{'id':'abc'}})+'\n')
            self.assertEqual(find_rollout(root,'abc'),p)

    def test_observer_is_not_started_until_insertion_commits(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);p=root/'2026/10/16/rollout-abc.jsonl';p.parent.mkdir(parents=True)
            p.write_text(json.dumps({'type':'session_meta','payload':{'id':'abc'}})+'\n')
            binding=Binding('w1:p2','/tmp/herdr.sock','terminal','abc','codex')
            herdr=Mock();herdr.inspect.return_value=binding
            received=[];done=threading.Event()
            def final(*args):received.append(args);done.set()
            replies=CodexReplies(root,herdr,final,Mock())
            try:
                token=replies.arm(binding)
                with p.open('a') as f:f.write(json.dumps(user())+'\n'+json.dumps(complete())+'\n')
                self.assertFalse(done.wait(.1))
                replies.commit(token)
                self.assertTrue(done.wait(3))
                self.assertEqual(len(received),1)
                self.assertEqual(received[0][-2:],('new','The English answer.'))
            finally:replies.close()

    def test_revoking_before_commit_leaves_no_reader(self):
        with tempfile.TemporaryDirectory() as temp:
            replies=CodexReplies(Path(temp),Mock(),Mock(),Mock())
            token=replies.arm(Binding('w1:p2','/tmp/sock','term',None,'codex'))
            replies.revoke(token)
            self.assertFalse(replies.items)
            replies.close()

    def test_new_session_is_resolved_after_enter_and_only_its_new_final_is_spoken(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            initial = Binding('w1:p4','/tmp/sock','terminal',None,'codex')
            resolved = Binding('w1:p4','/tmp/sock','terminal','abc','codex')
            herdr = Mock();herdr.inspect.return_value = initial
            received = [];done = threading.Event()
            def final(*args):received.append(args);done.set()
            replies = CodexReplies(root,herdr,final,Mock())
            try:
                token = replies.arm(initial)
                p = root/'2026/10/16/rollout-abc.jsonl';p.parent.mkdir(parents=True)
                old = user('old');old['timestamp'] = '2020-01-01T00:00:00Z'
                row = user();row.pop('metadata')
                row['payload']['internal_chat_message_metadata_passthrough'] = {'turn_id':'new'}
                p.write_text('\n'.join(json.dumps(r) for r in [
                    {'type':'session_meta','payload':{'id':'abc'}},old,row,complete()])+'\n')
                herdr.inspect.return_value = resolved
                replies.commit(token)
                self.assertTrue(done.wait(3))
                self.assertEqual(len(received),1)
                self.assertEqual(received[0][-3:],('abc','new','The English answer.'))
            finally:replies.close()


class ObservationRejectionTests(unittest.TestCase):
    def test_long_reply_waits_for_session_to_be_confirmed_again_before_speaking(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);p=root/'2026/10/16/rollout-abc.jsonl';p.parent.mkdir(parents=True)
            p.write_text(json.dumps({'type':'session_meta','payload':{'id':'abc'}})+'\n')
            binding=Binding('w1:p2','/tmp/sock','terminal','abc','codex')
            herdr=Mock();herdr.inspect.return_value=Binding('w1:p2','/tmp/sock','terminal',None,'codex')
            received=threading.Event()
            replies=CodexReplies(root,herdr,lambda *a:received.set(),Mock())
            try:
                token=replies.arm(binding)
                with p.open('a') as f:f.write(json.dumps(user())+'\n'+json.dumps(complete())+'\n')
                replies.commit(token)
                self.assertFalse(received.wait(1.1))
                herdr.inspect.return_value=binding
                self.assertTrue(received.wait(3))
            finally:replies.close()

    def test_pending_final_is_discarded_if_a_different_session_becomes_visible(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);p=root/'2026/10/16/rollout-abc.jsonl';p.parent.mkdir(parents=True)
            p.write_text(json.dumps({'type':'session_meta','payload':{'id':'abc'}})+'\n')
            binding=Binding('w1:p2','/tmp/sock','terminal','abc','codex')
            herdr=Mock();herdr.inspect.return_value=Binding('w1:p2','/tmp/sock','terminal',None,'codex')
            final=Mock();notified=threading.Event()
            replies=CodexReplies(root,herdr,final,lambda *a:notified.set())
            try:
                token=replies.arm(binding)
                with p.open('a') as f:f.write(json.dumps(user())+'\n'+json.dumps(complete())+'\n')
                replies.commit(token)
                time.sleep(1.1)
                herdr.inspect.return_value=Binding('w1:p2','/tmp/sock','terminal','def','codex')
                self.assertTrue(notified.wait(3));final.assert_not_called()
            finally:replies.close()

    def test_old_retained_user_record_uses_original_create_time(self):
        record = user()
        record['payload']['internal_chat_message_metadata_passthrough'] = {'create_time': 100.0}
        self.assertEqual(CodexReplies.record_time(record), 100.0)

    def test_changed_thread_cancels_without_reading_new_session(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);p=root/'2026/10/16/rollout-abc.jsonl';p.parent.mkdir(parents=True)
            p.write_text(json.dumps({'type':'session_meta','payload':{'id':'abc'}})+'\n')
            binding=Binding('w1:p2','/tmp/sock','terminal','abc','codex')
            herdr=Mock();herdr.inspect.return_value=Binding('w1:p2','/tmp/sock','terminal','def','codex')
            final=Mock();notified=threading.Event()
            replies=CodexReplies(root,herdr,final,lambda *_:notified.set())
            try:
                token=replies.arm(binding);replies.commit(token)
                self.assertTrue(notified.wait(3));final.assert_not_called()
            finally:replies.close()

    def test_f7_revocation_suppresses_pending_final(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);p=root/'2026/10/16/rollout-abc.jsonl';p.parent.mkdir(parents=True)
            p.write_text(json.dumps({'type':'session_meta','payload':{'id':'abc'}})+'\n')
            binding=Binding('w1:p2','/tmp/sock','terminal','abc','codex')
            herdr=Mock();herdr.inspect.return_value=binding;final=Mock()
            replies=CodexReplies(root,herdr,final,Mock())
            try:
                token=replies.arm(binding);replies.commit(token)
                replies.cancel(binding.pane,binding.socket)
                with p.open('a') as f:f.write(json.dumps(user())+'\n'+json.dumps(complete())+'\n')
                self.assertFalse(replies.items);final.assert_not_called()
            finally:replies.close()
