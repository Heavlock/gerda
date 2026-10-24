from __future__ import annotations
import fcntl
import os
import re
from pathlib import Path
import signal
import subprocess
import time
import uuid
import wave
from ...entity import VoiceError


class PipeWireCapture:
    def __init__(self, directory: Path, assistant_lock: Path):
        self.directory = directory
        self.assistant_lock = assistant_lock
        self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.jobs: dict[str, tuple[subprocess.Popen, object, object]] = {}

    def path(self, capture: str) -> Path:
        if not capture.isalnum():
            raise VoiceError('Некорректная запись')
        return self.directory / (capture + '.wav')

    def start(self) -> str:
        self.assistant_lock.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        lock = self.assistant_lock.open('a')
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            lock.close()
            raise VoiceError('Микрофон занят другой голосовой операцией') from None
        capture = uuid.uuid4().hex
        log_path = self.directory / (capture + '.log')
        log = log_path.open('wb')
        try:
            process = subprocess.Popen(['pw-record', '--rate', '16000', '--channels', '1',
                                        '--format', 's16', str(self.path(capture))],
                                       stdin=subprocess.DEVNULL, stdout=log, stderr=log,
                                       pass_fds=(lock.fileno(),), start_new_session=True)
            self.jobs[capture] = process, lock, log
            time.sleep(0.2)
            if process.poll() is not None:
                raise VoiceError('PipeWire не смог открыть микрофон')
            return capture
        except Exception:
            if capture in self.jobs:
                self.finish(capture)
            else:
                lock.close()
                log.close()
                log_path.unlink(missing_ok=True)
            raise

    def stop(self, capture: str) -> None:
        if capture not in self.jobs:
            raise VoiceError('Активная запись недоступна')
        process = self.jobs[capture][0]
        if process.poll() is not None:
            raise VoiceError('Запись прервалась; текст не вставлен')
        self._stop(process)
        path = self.path(capture)
        if not path.exists() or path.stat().st_size > 128 * 1024 * 1024:
            raise VoiceError('Запись отсутствует или слишком велика')
        try:
            with wave.open(str(path)) as audio:
                if audio.getnchannels() != 1 or audio.getframerate() != 16000 or audio.getsampwidth() != 2:
                    raise ValueError('Unexpected audio format')
                if audio.getnframes() < 1600:
                    raise VoiceError('Запись слишком короткая')
        except (wave.Error, EOFError, ValueError):
            raise VoiceError('Не удалось завершить аудиозапись') from None

    @staticmethod
    def _stop(process: subprocess.Popen) -> None:
        for sig, timeout in [(signal.SIGINT, 5), (signal.SIGTERM, 1), (signal.SIGKILL, 1)]:
            if process.poll() is not None:
                return
            process.send_signal(sig)
            try:
                process.wait(timeout=timeout)
                return
            except subprocess.TimeoutExpired:
                continue

    def finish(self, capture: str) -> None:
        job = self.jobs.pop(capture, None)
        if job is not None:
            process, lock, log = job
            try:
                self._stop(process)
            finally:
                log.close()
                lock.close()
        self.path(capture).unlink(missing_ok=True)
        (self.directory / (capture + '.log')).unlink(missing_ok=True)

    def clean_stale(self) -> None:
        if self.jobs:
            return
        for path in self.directory.iterdir():
            if re.fullmatch(r'[a-f0-9]{32}\.(wav|log)', path.name):
                path.unlink(missing_ok=True)

    def close(self) -> None:
        for capture in list(self.jobs):
            self.finish(capture)
