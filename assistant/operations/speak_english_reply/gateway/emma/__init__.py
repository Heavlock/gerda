from __future__ import annotations
from dataclasses import dataclass
import json
import logging
import os
from pathlib import Path
import queue
import selectors
import signal
import subprocess
import threading
import time
from typing import Callable
import uuid


class PaneGateway:
    def __init__(self, inspect: Callable):
        self.inspect = inspect

    def matches(self, pane: str, socket: str, terminal: str, session: str) -> bool:
        try:
            actual_terminal, actual_session, agent = self.inspect(pane, socket)
            return actual_terminal == terminal and actual_session == session and agent == 'codex'
        except Exception:
            return False


@dataclass(frozen=True)
class SpeechJob:
    identifier: str
    epoch: int
    binding: tuple[str, str, str, str]
    text: str


class EmmaSpeech:
    def __init__(self, root: Path, runtime: Path, audio_lock: Path,
                 valid: Callable, notify: Callable[[str], None]):
        self.root = root
        self.runtime = runtime
        self.audio_lock = audio_lock
        self.valid = valid
        self.notify = notify
        self.queue: queue.Queue[SpeechJob] = queue.Queue(maxsize=4)
        self.worker_lock = threading.RLock()
        self.state = threading.RLock()
        self.process: subprocess.Popen | None = None
        self.ready: dict | None = None
        self.current: SpeechJob | None = None
        self.epoch = 0
        self.idle = threading.Event()
        self.idle.set()
        self.closed = threading.Event()
        self.used = time.monotonic()
        self.prewarming = False
        self.seen: set[tuple] = set()
        self.consumer = threading.Thread(target=self._consume, daemon=True)
        self.consumer.start()

    def _receive(self, process: subprocess.Popen, timeout: float, job: SpeechJob | None = None) -> dict:
        deadline = time.monotonic() + timeout
        with selectors.DefaultSelector() as selector:
            selector.register(process.stdout, selectors.EVENT_READ)
            while time.monotonic() < deadline:
                if selector.select(timeout=0.5):
                    line = process.stdout.readline(65537)
                    if not line or len(line) > 65536 or not line.endswith(b'\n'):
                        raise RuntimeError('Emma worker closed or returned invalid data')
                    return json.loads(line)
                if process.poll() is not None:
                    raise RuntimeError('Emma worker stopped')
                if job is not None:
                    with self.state:
                        obsolete = job.epoch != self.epoch
                    if obsolete or not self.valid(*job.binding):
                        (self.runtime / ('cancel-' + job.identifier)).touch()
        raise TimeoutError('Emma worker timeout')

    def _load(self) -> subprocess.Popen:
        if self.closed.is_set():
            raise RuntimeError('Emma is closing')
        if self.process is not None and self.process.poll() is None:
            return self.process
        env = dict(os.environ)
        env.update(PYTHONPATH=str(self.root), HF_HUB_OFFLINE='1', HF_HUB_DISABLE_TELEMETRY='1',
                   OMP_NUM_THREADS='2', OPENBLAS_NUM_THREADS='2', MKL_NUM_THREADS='2',
                   CUDA_CACHE_PATH=str(self.runtime / 'cuda-cache'),
                   NUMBA_CACHE_DIR=str(self.runtime / 'numba-cache'))
        self.process = subprocess.Popen([str(self.root / '.venv-english/bin/python'), '-m',
                'assistant.operations.speak_english_reply.gateway.emma.worker',
                '--root', str(self.root), '--runtime', str(self.runtime)],
                env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                stderr=None, start_new_session=True, bufsize=0)
        process = self.process
        ready = self._receive(process, 120)
        if ready.get('event') != 'ready' or ready.get('voice') != 'en-Emma_woman.pt':
            self._terminate()
            raise RuntimeError('Unexpected voice worker')
        self.ready = ready
        logging.info('Emma ready: device=%s threads=%s', ready['device'], ready.get('threads'))
        if ready['device'] == 'cpu':
            self.notify('GPU недоступен: английская озвучка работает на CPU, 8 потоков')
        return process

    def prewarm(self) -> None:
        with self.state:
            if self.prewarming or self.closed.is_set():
                return
            self.prewarming = True
        def load():
            try:
                with self.worker_lock:
                    self._load()
                    self.used = time.monotonic()
            except Exception:
                self._terminate()
                if not self.closed.is_set():
                    self.notify('Не удалось подготовить английскую озвучку; проверь журнал gerda-english')
            finally:
                with self.state:
                    self.prewarming = False
        threading.Thread(target=load, daemon=True).start()

    def submit(self, pane: str, socket: str, terminal: str, session: str,
               turn: str, text: str) -> None:
        key = socket, pane, session, turn
        with self.state:
            if key in self.seen:
                return
            if len(self.seen) >= 128:
                self.seen.clear()
            self.seen.add(key)
            job = SpeechJob(uuid.uuid4().hex, self.epoch, (pane, socket, terminal, session), text)
            try:
                self.queue.put_nowait(job)
            except queue.Full:
                self.seen.discard(key)
                self.notify('Очередь английской озвучки заполнена')

    def _consume(self) -> None:
        while not self.closed.is_set():
            try:
                job = self.queue.get(timeout=1)
            except queue.Empty:
                if time.monotonic() - self.used > 300 and self.worker_lock.acquire(blocking=False):
                    try:
                        self._terminate()
                    finally:
                        self.worker_lock.release()
                continue
            with self.state:
                if job.epoch != self.epoch:
                    continue
                self.current = job
                self.idle.clear()
            try:
                if not self.valid(*job.binding):
                    continue
                with self.worker_lock:
                    process = self._load()
                    request = {'id': job.identifier, 'text': job.text, 'audio_lock': str(self.audio_lock)}
                    process.stdin.write((json.dumps(request) + '\n').encode())
                    process.stdin.flush()
                    reply = self._receive(process, 7205, job)
                    if reply.get('id') != job.identifier or reply.get('event') != 'done':
                        raise RuntimeError('Speech failed')
                    logging.info('Emma playback finished: cancelled=%s audio_seconds=%s',
                                 reply.get('cancelled'), reply.get('audio_seconds'))
                    self.used = time.monotonic()
            except Exception:
                logging.exception('Emma playback failed')
                self._terminate()
                with self.state:
                    cancelled = job.epoch != self.epoch
                if not cancelled and not self.closed.is_set():
                    self.notify('Ошибка английской озвучки; повторная отправка запроса не выполнялась')
            finally:
                (self.runtime / ('cancel-' + job.identifier)).unlink(missing_ok=True)
                with self.state:
                    self.current = None
                    self.idle.set()

    def cancel(self) -> None:
        with self.state:
            self.epoch += 1
            while True:
                try:
                    self.queue.get_nowait()
                except queue.Empty:
                    break
            if self.current:
                (self.runtime / ('cancel-' + self.current.identifier)).touch()
        if not self.idle.wait(timeout=3):
            self._terminate()
            if not self.idle.wait(timeout=3):
                raise RuntimeError('Не удалось остановить озвучку перед записью')

    def _terminate(self) -> None:
        process = self.process
        if process is not None:
            if process.poll() is None:
                try:
                    os.killpg(process.pid, signal.SIGTERM)
                    process.wait(timeout=3)
                except ProcessLookupError:
                    pass
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.wait(timeout=2)
            for stream in [process.stdin, process.stdout]:
                if stream:
                    try:
                        stream.close()
                    except OSError:
                        pass
            if self.process is process:
                self.process = None
                self.ready = None

    def close(self) -> None:
        self.closed.set()
        self.cancel()
        self._terminate()
        self.consumer.join(timeout=3)
