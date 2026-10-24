"""Composition root for the on-demand native F8 recognition worker."""
from __future__ import annotations

import argparse
import logging
import os
from pathlib import Path
import signal
import threading

from .operations.transcribe_russian_dictation.gateway.gigaam import GigaamRecognizer
from .operations.transcribe_russian_dictation.presentation.ipc import Handler
from .operations.transcribe_russian_dictation.usecase import TranscribeRussianDictation
from .technical.voiceipc import serve


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    runtime = Path(os.getenv('XDG_RUNTIME_DIR', f'/run/user/{os.getuid()}'))
    threads = int(os.getenv('GERDA_RUSSIAN_THREADS', '2'))
    idle_seconds = float(os.getenv('GERDA_RUSSIAN_IDLE_SECONDS', '300'))
    if not 1 <= threads <= 32 or idle_seconds <= 0:
        parser.error('Invalid Russian worker resource settings')
    logging.basicConfig(level=logging.INFO, format='%(levelname)s %(message)s')
    recognizer = GigaamRecognizer(root / 'models/gigaam-v3-e2e-rnnt',
                                 root / 'models/silero-vad', runtime / 'herdr-dictation', threads=threads)
    handler = Handler(TranscribeRussianDictation(recognizer))
    stopped = threading.Event()
    for signum in (signal.SIGTERM, signal.SIGINT):
        signal.signal(signum, lambda *_: stopped.set())
    recognizer.load()
    if args.check:
        print('Russian GigaAM loaded on CPU; microphone and Herdr not started')
        return
    serve(runtime / 'gerda-russian/control.sock', handler.execute, stopped, idle_timeout=idle_seconds)
    logging.info('Russian worker stopped; model memory released')


if __name__ == '__main__':
    main()
