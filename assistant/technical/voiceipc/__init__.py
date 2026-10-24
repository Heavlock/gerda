from __future__ import annotations
from concurrent.futures import ThreadPoolExecutor
import json
import logging
import os
from pathlib import Path
import socket
import stat
import struct
import threading
import time
from typing import Callable


LIMIT = 4096


def request(path: Path, body: dict, timeout: float = 180, *, response_limit: int = LIMIT) -> dict:
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
        client.settimeout(timeout)
        client.connect(str(path))
        client.sendall(json.dumps(body).encode() + b'\n')
        with client.makefile('rb') as stream:
            line = stream.readline(response_limit + 1)
        if not line.endswith(b'\n') or len(line) > response_limit:
            raise ValueError('Invalid local response')
        return json.loads(line)


def serve(path: Path, handler: Callable[[dict], dict], stopped: threading.Event, on_bound: Callable[[], None] | None = None, *, idle_timeout: float | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if path.parent.stat().st_uid != os.getuid() or path.parent.is_symlink():
        raise ValueError('Untrusted local runtime directory')
    path.parent.chmod(0o700)
    if path.exists():
        status = path.lstat()
        if status.st_uid != os.getuid() or not stat.S_ISSOCK(status.st_mode):
            raise ValueError('Untrusted existing local socket')
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as probe:
            probe.settimeout(0.3)
            try:
                probe.connect(str(path))
            except (ConnectionRefusedError, FileNotFoundError):
                path.unlink(missing_ok=True)
            else:
                raise RuntimeError('Local voice service already running')
    permits = threading.BoundedSemaphore(8)
    activity = threading.Lock()
    last_activity = time.monotonic()
    active = 0
    def respond(connection):
        nonlocal last_activity, active
        try:
            connection.settimeout(5)
            uid = struct.unpack('3i', connection.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12))[1]
            if uid != os.getuid():
                return
            with connection.makefile('rb') as stream:
                line = stream.readline(LIMIT + 1)
                if len(line) > LIMIT or not line.endswith(b'\n'):
                    raise ValueError('Local request exceeds limit')
                payload = json.loads(line)
                if not isinstance(payload, dict):
                    raise ValueError('Invalid local request')
                result = handler(payload)
            connection.sendall(json.dumps(result, ensure_ascii=False).encode() + b'\n')
        except Exception:
            logging.exception('Local English voice operation failed')
            try:
                connection.sendall(b'{"status":"error","message":"Local voice operation failed; check gerda-english journal"}\n')
            except OSError:
                pass
        finally:
            connection.close()
            with activity:
                active -= 1
                last_activity = time.monotonic()
            permits.release()
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as listener, ThreadPoolExecutor(max_workers=4) as pool:
        listener.bind(str(path))
        path.chmod(0o600)
        if on_bound is not None:
            on_bound()
        listener.listen(8)
        listener.settimeout(0.5)
        try:
            while not stopped.is_set():
                with activity:
                    if idle_timeout is not None and active == 0 and time.monotonic() - last_activity >= idle_timeout:
                        break
                try:
                    connection, _ = listener.accept()
                except socket.timeout:
                    continue
                if permits.acquire(blocking=False):
                    with activity:
                        active += 1
                    pool.submit(respond, connection)
                else:
                    connection.close()
        finally:
            path.unlink(missing_ok=True)
