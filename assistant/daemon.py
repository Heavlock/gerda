"""Composition root for the separate English Gerda modes."""
from __future__ import annotations
import argparse
import logging
from dataclasses import asdict
import os
from pathlib import Path
import signal
import threading
from .hotkey import notify
from .technical.voiceipc import serve
from .operations.toggle_english_dictation.repository.memory import RecordingRepository
from .operations.toggle_english_dictation.gateway.pipewire import PipeWireCapture
from .operations.toggle_english_dictation.gateway.whisper import WhisperRecognizer
from .operations.toggle_english_dictation.gateway.herdr import HerdrGateway
from .operations.toggle_english_dictation.gateway.codex import CodexReplies
from .operations.toggle_english_dictation.presentation.ipc import Handler as DictationHandler
from .operations.toggle_english_dictation.usecase import ToggleEnglishDictation
from .operations.speak_english_reply.gateway.emma import EmmaSpeech, PaneGateway
from .operations.speak_english_reply.presentation.event import Handler as ReplyHandler
from .operations.speak_english_reply.usecase import SpeakEnglishReply


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--check', action='store_true', help='Load both English models without microphone/playback')
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    runtime = Path(os.getenv('XDG_RUNTIME_DIR', f'/run/user/{os.getuid()}')) / 'gerda-english'
    runtime.mkdir(parents=True, exist_ok=True, mode=0o700)
    runtime.chmod(0o700)
    audio_lock = runtime.parent / 'herdr-dictation/assistant.lock'
    binary = Path(os.getenv('HERDR_BIN_PATH', str(Path.home() / '.local/bin/herdr')))
    sessions = Path(os.getenv('CODEX_HOME', str(Path.home() / '.codex'))) / 'sessions'
    logging.basicConfig(level=logging.INFO, format='%(levelname)s %(message)s')
    herdr = HerdrGateway(binary, sessions.parent / 'history.jsonl')
    capture = PipeWireCapture(runtime / 'capture', audio_lock)
    recognizer = WhisperRecognizer(root / 'models/whisper-medium.en', capture.path)
    def inspect_identity(pane, socket):
        binding = herdr.inspect(pane, socket)
        return binding.terminal, binding.session, binding.agent
    pane = PaneGateway(inspect_identity)
    speech = EmmaSpeech(root, runtime, audio_lock, pane.matches, notify)
    reply_handler = ReplyHandler(SpeakEnglishReply(pane, speech), notify)
    replies = CodexReplies(sessions, herdr, reply_handler.execute, notify)
    usecase = ToggleEnglishDictation(RecordingRepository(), capture, recognizer, herdr, replies, speech)
    handler = DictationHandler(usecase)
    stopped = threading.Event()
    for signum in [signal.SIGTERM, signal.SIGINT]:
        signal.signal(signum, lambda *_: stopped.set())
    try:
        if args.check:
            recognizer.load()
            with speech.worker_lock:
                speech._load()
                print(speech.ready, flush=True)
            print('English models loaded; microphone and playback not started', flush=True)
            return
        serve(runtime / 'control.sock', lambda body: asdict(handler.execute(body)), stopped, capture.clean_stale)
    finally:
        replies.close()
        capture.close()
        speech.close()


if __name__ == '__main__':
    main()
