"""Install the native F8 worker and launcher, retaining the original launcher."""
from __future__ import annotations

import fcntl
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import tempfile


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    runtime = Path(os.getenv('XDG_RUNTIME_DIR', f'/run/user/{os.getuid()}')) / 'herdr-dictation'
    runtime.mkdir(parents=True, exist_ok=True, mode=0o700)
    # Both locks must be free: never replace the launcher during capture or ASR.
    with (runtime / 'lock').open('a') as operation_lock, (runtime / 'assistant.lock').open('a') as audio_lock:
        for lock in (operation_lock, audio_lock):
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        unit_dir = Path.home() / '.config/systemd/user'
        unit_dir.mkdir(parents=True, exist_ok=True)
        escaped = str(root).replace('\\', '\\\\').replace('"', '\\"').replace('%', '%%')
        unit_text = (root / 'systemd/gerda-russian.service').read_text().replace('@ROOT@', escaped)
        source = (root / 'scripts/herdr-dictate.sh').read_text()
        launcher_text = source.replace('gerda_root="@ROOT@"', 'gerda_root=' + shlex.quote(str(root)))
        with tempfile.TemporaryDirectory(prefix='gerda-russian-install-') as temp:
            staged_unit = Path(temp) / 'gerda-russian.service'
            staged_unit.write_text(unit_text)
            staged_launcher = Path(temp) / 'herdr-dictate'
            staged_launcher.write_text(launcher_text)
            subprocess.run(['systemd-analyze', '--user', 'verify', str(staged_unit)], check=True)
            subprocess.run(['bash', '-n', str(staged_launcher)], check=True)
        launcher = Path.home() / '.local/bin/herdr-dictate'
        launcher.parent.mkdir(parents=True, exist_ok=True)
        backup = launcher.with_name('herdr-dictate.before-f8-optimization')
        if launcher.exists() and not backup.exists():
            shutil.copy2(launcher, backup)
            backup.chmod(0o600)
        unit = unit_dir / 'gerda-russian.service'
        previous_unit = unit.read_bytes() if unit.exists() else None
        previous_launcher = launcher.read_bytes() if launcher.exists() else None
        try:
            unit.write_text(unit_text)
            subprocess.run(['systemctl', '--user', 'daemon-reload'], check=True)
            temp_launcher = launcher.with_name('herdr-dictate.new')
            temp_launcher.write_text(launcher_text)
            temp_launcher.chmod(0o755)
            temp_launcher.replace(launcher)
        except Exception:
            if previous_unit is None:
                unit.unlink(missing_ok=True)
            else:
                unit.write_bytes(previous_unit)
            if previous_launcher is not None:
                launcher.write_bytes(previous_launcher)
                launcher.chmod(0o755)
            subprocess.run(['systemctl', '--user', 'daemon-reload'], check=False)
            raise
    print('F8 optimized: on-demand CPU2 recognition, five-minute idle exit; original launcher backed up')


if __name__ == '__main__':
    main()
