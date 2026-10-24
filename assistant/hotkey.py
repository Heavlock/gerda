from __future__ import annotations
import argparse
import os
from pathlib import Path
import subprocess
from .technical.voiceipc import request


def notify(message: str) -> None:
    try:
        subprocess.run(['notify-send', '-a', 'Герда · English', message],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=3)
    except (OSError, subprocess.TimeoutExpired):
        pass


def main() -> None:
    parser = argparse.ArgumentParser(description='F7 English dictation / F6 English spoken reply')
    parser.add_argument('mode', choices=['dictate', 'speak'])
    args = parser.parse_args()
    pane = os.getenv('HERDR_ACTIVE_PANE_ID') or os.getenv('HERDR_PANE_ID')
    if not pane:
        notify('Запускай английскую диктовку клавишами F7/F6 в Herdr')
        raise SystemExit(1)
    runtime = Path(os.getenv('XDG_RUNTIME_DIR', f'/run/user/{os.getuid()}')) / 'gerda-english'
    socket = os.getenv('HERDR_SOCKET_PATH', str(Path.home() / '.config/herdr/herdr.sock'))
    try:
        result = request(runtime / 'control.sock', {'mode': args.mode, 'pane': pane, 'socket': socket})
        notify(result.get('message', result.get('status', 'Готово')))
        print(result.get('status', 'error'))
        raise SystemExit(1 if result.get('status') == 'error' else 0)
    except (OSError, ValueError):
        notify('Английский режим недоступен: проверь gerda-english.service')
        raise SystemExit(1) from None


if __name__ == '__main__':
    main()
