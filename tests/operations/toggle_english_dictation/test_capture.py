from __future__ import annotations
import fcntl
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from assistant.operations.toggle_english_dictation.entity import VoiceError
from assistant.operations.toggle_english_dictation.gateway.pipewire import PipeWireCapture


class CaptureTests(unittest.TestCase):
    def test_existing_f8_microphone_lock_prevents_new_capture(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);lock=root/'assistant.lock'
            capture=PipeWireCapture(root/'capture',lock)
            with lock.open('a') as owner:
                fcntl.flock(owner,fcntl.LOCK_EX|fcntl.LOCK_NB)
                with patch('subprocess.Popen') as spawn:
                    with self.assertRaises(VoiceError):capture.start()
                    spawn.assert_not_called()
            capture.close()

    def test_failed_spawn_removes_own_log_and_releases_lock(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);capture=PipeWireCapture(root/'capture',root/'lock')
            with patch('subprocess.Popen',side_effect=OSError('failure')):
                with self.assertRaises(OSError):capture.start()
            self.assertFalse(list((root/'capture').iterdir()))
            with (root/'lock').open('a') as owner:fcntl.flock(owner,fcntl.LOCK_EX|fcntl.LOCK_NB)

    def test_stale_cleanup_removes_only_isolated_capture_files(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);capture=PipeWireCapture(root/'capture',root/'lock')
            owned=root/'capture'/('a'*32+'.wav');owned.write_bytes(b'old')
            unrelated=root/'capture'/'keep.txt';unrelated.write_text('keep')
            capture.clean_stale()
            self.assertFalse(owned.exists());self.assertTrue(unrelated.exists())
