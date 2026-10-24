from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
import logging
import threading
import time
from typing import Callable
import uuid
from ...entity import Binding, VoiceError
from .transcript import NextTurn, Tail, find_rollout


@dataclass
class Registration:
    binding: Binding
    created: float
    tail: Tail | None
    token: str = field(default_factory=lambda: uuid.uuid4().hex)
    stop: threading.Event = field(default_factory=threading.Event)
    thread: threading.Thread | None = None


class CodexReplies:
    def __init__(self, sessions: Path, herdr, on_final: Callable, notify: Callable[[str], None]):
        self.sessions = sessions
        self.herdr = herdr
        self.on_final = on_final
        self.notify = notify
        self.items: dict[str, Registration] = {}
        self.lock = threading.RLock()
        self.closed = False

    def arm(self, binding: Binding) -> str:
        with self.lock:
            self.cancel(binding.pane, binding.socket)
            if len(self.items) >= 8:
                raise VoiceError('Слишком много ожидающих голосовых ответов')
            tail = None
            if binding.session:
                path = find_rollout(self.sessions, binding.session)
                if path is None:
                    raise VoiceError('Локальная история этой сессии Codex недоступна; используй F7')
                tail = Tail(path, path.stat().st_size)
            item = Registration(binding, time.time(), tail)
            item.thread = threading.Thread(target=self._watch, args=(item,), daemon=True)
            self.items[item.token] = item
            logging.info('F6 reply armed: pane=%s session_known=%s', binding.pane, bool(binding.session))
            return item.token

    def commit(self, registration: str) -> None:
        with self.lock:
            item = self.items.get(registration)
            if item is None or item.stop.is_set():
                raise VoiceError('Ожидание озвучки отменено')
            item.thread.start()

    def cancel(self, pane: str, socket: str) -> None:
        with self.lock:
            for token, item in list(self.items.items()):
                if (item.binding.pane, item.binding.socket) == (pane, socket):
                    item.stop.set()
                    self.items.pop(token, None)

    def revoke(self, registration: str) -> None:
        with self.lock:
            item = self.items.pop(registration, None)
            if item:
                item.stop.set()

    @staticmethod
    def record_time(record: dict) -> float | None:
        payload = record.get('payload') or {}
        if not isinstance(payload, dict):
            return None
        passthrough = payload.get('internal_chat_message_metadata_passthrough') or {}
        if not isinstance(passthrough, dict):
            return None
        if payload.get('role') == 'user' and isinstance(passthrough.get('create_time'), (int, float)):
            return passthrough['create_time']
        try:
            return datetime.fromisoformat(record.get('timestamp', '').replace('Z', '+00:00')).timestamp()
        except (ValueError, TypeError, AttributeError):
            return None

    def _watch(self, item: Registration) -> None:
        turn = NextTurn()
        pending_final = None
        pending_since = None
        session = item.binding.session
        started = time.monotonic()
        try:
            while not item.stop.wait(0.5) and not self.closed:
                current = self.herdr.inspect(item.binding.pane, item.binding.socket)
                if current.session_error:
                    raise VoiceError(current.session_error)
                if current.terminal != item.binding.terminal or current.agent != 'codex':
                    raise ValueError('Pane replaced')
                if session and current.session is not None and current.session != session:
                    raise ValueError('Codex session changed')
                if not session and current.session:
                    session = current.session
                    logging.info('F6 session resolved: pane=%s', item.binding.pane)
                if item.tail is None and session:
                    path = find_rollout(self.sessions, session)
                    if path:
                        item.tail = Tail(path, 0)
                if item.tail is not None and pending_final is None:
                    for record in item.tail.read():
                        timestamp = self.record_time(record)
                        if timestamp is None or timestamp < item.created:
                            continue
                        text = turn.feed(record)
                        if text and not item.stop.is_set():
                            pending_final = text
                            pending_since = time.monotonic()
                            break
                        if turn.finished:
                            return
                if pending_final is not None:
                    # A long running reply may hide the prompt. Wait for the idle
                    # pane's history to confirm the session again before speech.
                    actual = self.herdr.inspect(item.binding.pane, item.binding.socket)
                    if actual.terminal != item.binding.terminal or actual.agent != 'codex' or actual.session_error:
                        raise ValueError('Reply occupant unavailable')
                    if actual.session is not None:
                        if actual.session != session:
                            raise ValueError('Reply occupant changed')
                        with self.lock:
                            if item.stop.is_set() or item.token not in self.items:
                                return
                            self.on_final(item.binding.pane, item.binding.socket,
                                          item.binding.terminal, session, turn.turn, pending_final)
                            logging.info('F6 final dispatched: pane=%s', item.binding.pane)
                        return
                    if time.monotonic() - pending_since > 30:
                        raise ValueError('Completed reply session could not be confirmed')
                timeout = 6 * 3600 if turn.turn else 1800
                if time.monotonic() - started > timeout:
                    raise ValueError('Reply wait expired')
        except (OSError, ValueError, VoiceError) as error:
            if not item.stop.is_set() and not self.closed:
                logging.warning('F6 observation stopped: %s', type(error).__name__)
                self.notify('Озвучка отменена: панель, сессия или локальная история недоступна')
        finally:
            with self.lock:
                self.items.pop(item.token, None)

    def close(self) -> None:
        self.closed = True
        with self.lock:
            items = list(self.items.values())
            for item in items:
                item.stop.set()
            self.items.clear()
        for item in items:
            if item.thread and item.thread.ident is not None:
                item.thread.join(timeout=1)
