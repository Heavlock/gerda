"""CLI composition root for submitting a saved F8 recording."""
from __future__ import annotations

import argparse
import os
from pathlib import Path

from .operations.transcribe_russian_dictation.entity import RecognitionError
from .operations.transcribe_russian_dictation.gateway.ipc import RemoteUsecase
from .operations.transcribe_russian_dictation.presentation.cli import Handler


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('capture')
    args = parser.parse_args()
    runtime = Path(os.getenv('XDG_RUNTIME_DIR', f'/run/user/{os.getuid()}'))
    handler = Handler(RemoteUsecase(runtime / 'gerda-russian/control.sock'))
    try:
        print(handler.execute(args.capture))
    except (RecognitionError, ValueError) as error:
        parser.exit(1, str(error) + '\n')


if __name__ == '__main__':
    main()
