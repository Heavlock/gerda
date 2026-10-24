"""Install the English user service and optional Herdr F6/F7 bindings."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import time
import tomllib


def add_bindings(original: str, wrapper: Path) -> str:
    commands = tomllib.loads(original).get('keys', {}).get('command', [])
    additions = []
    for key, mode, description in [
        ('f7', 'dictate', 'English dictation: start/stop'),
        ('f6', 'speak', 'English dictation and spoken Codex reply'),
    ]:
        command = shlex.quote(str(wrapper)) + ' ' + mode
        matching = [v for v in commands if v.get('key', '').lower() == key]
        if matching:
            if (len(matching) == 1 and matching[0].get('command') == command
                    and matching[0].get('type') == 'shell'):
                continue
            raise ValueError(f'{key.upper()} is already bound; edit it or use --no-keybindings')
        additions.append('\n[[keys.command]]\n' + '\n'.join(
            f'{name} = {json.dumps(value, ensure_ascii=False)}'
            for name, value in [('key', key), ('type', 'shell'),
                                ('command', command), ('description', description)]
        ) + '\n')
    result = original + ''.join(additions)
    tomllib.loads(result)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--no-keybindings', action='store_true',
                        help='Install the service and launcher; configure keys manually')
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    home = Path.home()
    python = root / '.venv-english/bin/python'
    if not python.exists():
        parser.error('Install the English runtime first; see README.md')
    binary = os.getenv('HERDR_BIN_PATH') or shutil.which('herdr')
    if not binary:
        parser.error('herdr must be on PATH, or set HERDR_BIN_PATH to its executable')
    binary = str(Path(binary).absolute())
    config = Path(os.getenv('HERDR_CONFIG_PATH', str(home / '.config/herdr/config.toml'))).expanduser()
    original = config.read_text() if config.exists() else ''
    wrapper = home / '.local/bin/gerda-english'
    # Reject conflicting keys before writing launchers, units or config.
    new = original if args.no_keybindings else add_bindings(original, wrapper)
    wrapper.parent.mkdir(parents=True, exist_ok=True)
    wrapper.write_text('#!/usr/bin/env bash\nset -euo pipefail\nexport PYTHONPATH='
                       + shlex.quote(str(root)) + '\nexec ' + shlex.quote(str(python))
                       + ' -m assistant.hotkey "$@"\n')
    wrapper.chmod(0o755)
    unit_dir = home / '.config/systemd/user'
    unit_dir.mkdir(parents=True, exist_ok=True)
    escaped = str(root).replace('\\', '\\\\').replace('"', '\\"').replace('%', '%%')
    unit = unit_dir / 'gerda-english.service'
    unit_text = (root / 'systemd/gerda-english.service').read_text().replace('@ROOT@', escaped)
    binary_setting = ('HERDR_BIN_PATH=' + binary).replace('\\', '\\\\').replace('"', '\\"').replace('%', '%%')
    unit_text = unit_text.replace('[Service]\n', '[Service]\nEnvironment="' + binary_setting + '"\n')
    unit.write_text(unit_text)
    subprocess.run(['systemd-analyze', '--user', 'verify', str(unit)], check=True)
    subprocess.run(['systemctl', '--user', 'daemon-reload'], check=True)
    subprocess.run(['systemctl', '--user', 'enable', '--now', 'gerda-english.service'], check=True)
    ready = Path(os.environ.get('XDG_RUNTIME_DIR', f'/run/user/{os.getuid()}')) / 'gerda-english/control.sock'
    deadline = time.monotonic() + 15
    while not ready.exists() and time.monotonic() < deadline:
        time.sleep(0.1)
    if not ready.exists():
        raise RuntimeError('Service did not create its socket; see journalctl --user -u gerda-english')
    if not args.no_keybindings:
        config.parent.mkdir(parents=True, exist_ok=True)
        existed = config.exists()
        backup = config.with_name('config.toml.before-gerda-english')
        if existed and not backup.exists():
            shutil.copy2(config, backup)
            backup.chmod(0o600)
        temp = config.with_name(config.name + '.gerda-english-new')
        temp.write_text(new)
        temp.chmod(config.stat().st_mode & 0o777 if existed else 0o600)
        os.replace(temp, config)
        try:
            subprocess.run([binary, 'server', 'reload-config'], check=True)
        except Exception:
            if existed:
                temp.write_text(original)
                temp.chmod(config.stat().st_mode & 0o777)
                os.replace(temp, config)
            else:
                config.unlink()
            raise
    print('English service installed. ' + ('Configure keys using docs/herdr.md.'
          if args.no_keybindings else 'F7=dictation, F6=dictation+Emma; F8 unchanged.'))


if __name__ == '__main__':
    main()
