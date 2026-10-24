from __future__ import annotations

import fcntl
import json
import os
from pathlib import Path
import shlex
import signal
import subprocess
import tempfile
import unittest


class HotkeyContractTests(unittest.TestCase):
    """Run the actual launcher with fake audio, recognizer, systemd and Herdr."""

    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.temp = Path(temporary.name)
        self.root = self.temp / 'project'
        self.bin = self.temp / 'bin'
        self.bin.mkdir()
        (self.root / '.venv/bin').mkdir(parents=True)
        (self.root / 'assistant').mkdir()
        (self.root / 'assistant/russian_daemon.py').touch()
        model = self.root / 'models/gigaam-v3-e2e-rnnt'
        model.mkdir(parents=True)
        (model / 'v3_e2e_rnnt_encoder.int8.onnx').touch()
        source = Path(__file__).resolve().parents[3] / 'scripts/herdr-dictate.sh'
        self.launcher = self.temp / 'herdr-dictate'
        self.launcher.write_text(source.read_text().replace('gerda_root="@ROOT@"',
                                                           'gerda_root=' + shlex.quote(str(self.root))))
        self.runtime = self.temp / 'runtime'
        self.runtime.mkdir()
        self.log = self.temp / 'calls.jsonl'
        self.env = dict(os.environ, PATH=str(self.bin) + ':' + os.environ['PATH'],
                        XDG_RUNTIME_DIR=str(self.runtime), HERDR_ACTIVE_PANE_ID='saved-pane',
                        HERDR_BIN_PATH=str(self.bin / 'herdr'), TEST_CALLS=str(self.log),
                        TEST_TEXT='Русский текст.', TEST_FAIL='0')
        logging_command = '''#!/usr/bin/env python3
import json,os,sys
with open(os.environ['TEST_CALLS'],'a') as f:
 f.write(json.dumps([os.path.basename(sys.argv[0]),*sys.argv[1:]],ensure_ascii=False)+'\\n')
'''
        for name in ['herdr', 'systemctl', 'notify-send']:
            self.executable(self.bin / name, logging_command)
        self.executable(self.root / '.venv/bin/python', logging_command + '''
if os.environ['TEST_FAIL']=='1':sys.exit(1)
print(os.environ['TEST_TEXT'])
''')
        self.executable(self.bin / 'pw-record', '''#!/usr/bin/env python3
import signal,sys,time,wave
with wave.open(sys.argv[-1],'wb') as f:
 f.setnchannels(1);f.setsampwidth(2);f.setframerate(16000);f.writeframes(b'\\0'*32000)
signal.signal(signal.SIGINT,lambda *_:sys.exit(0))
signal.signal(signal.SIGTERM,lambda *_:sys.exit(0))
while True:time.sleep(.05)
''')
        self.addCleanup(self.stop_recorder)

    @staticmethod
    def executable(path: Path, text: str) -> None:
        path.write_text(text)
        path.chmod(0o755)

    def stop_recorder(self) -> None:
        pidfile = self.runtime / 'herdr-dictation/record.pid'
        if pidfile.exists():
            try:
                os.kill(int(pidfile.read_text()), signal.SIGTERM)
            except ProcessLookupError:
                pass

    def press(self, **settings: str) -> subprocess.CompletedProcess:
        return subprocess.run(['bash', str(self.launcher)], env=self.env | settings,
                              capture_output=True, text=True, timeout=12)

    def calls(self, name: str) -> list[list[str]]:
        return [row for line in self.log.read_text().splitlines()
                if (row := json.loads(line))[0] == name]

    def test_recording_prewarms_and_stop_inserts_once_into_saved_pane(self) -> None:
        self.assertEqual(self.press().returncode, 0)
        self.assertEqual(self.calls('systemctl'), [['systemctl', '--user', '--no-block', 'start', 'gerda-russian.service']])
        self.assertEqual(self.calls('python'), [])
        self.assertEqual(self.press(HERDR_ACTIVE_PANE_ID='another-pane').returncode, 0)
        self.assertEqual(self.calls('python'), [['python', '-m', 'assistant.russian_dictation', 'prompt']])
        self.assertEqual(self.calls('herdr'), [['herdr', 'pane', 'send-text', 'saved-pane', 'Русский текст.']])
        self.assertFalse((self.runtime / 'herdr-dictation/prompt.wav').exists())
        self.assertFalse((self.runtime / 'herdr-dictation/record.pid').exists())
        self.assertFalse((self.runtime / 'herdr-dictation/output/prompt.txt').exists())

    def test_failed_recognition_never_inserts_stale_text(self) -> None:
        self.assertEqual(self.press().returncode, 0)
        self.assertNotEqual(self.press(TEST_FAIL='1').returncode, 0)
        self.assertEqual(self.calls('herdr'), [])
        self.assertFalse((self.runtime / 'herdr-dictation/output/prompt.txt').exists())

    def test_empty_recognition_does_not_insert(self) -> None:
        self.assertEqual(self.press().returncode, 0)
        self.assertEqual(self.press(TEST_TEXT='').returncode, 0)
        self.assertEqual(self.calls('herdr'), [])
        self.assertFalse((self.runtime / 'herdr-dictation/prompt.wav').exists())

    def test_shared_microphone_lock_prevents_recording(self) -> None:
        directory = self.runtime / 'herdr-dictation'
        directory.mkdir()
        with (directory / 'assistant.lock').open('a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            self.assertNotEqual(self.press().returncode, 0)
        self.assertFalse((directory / 'record.pid').exists())
        self.assertEqual(self.calls('systemctl'), [])
