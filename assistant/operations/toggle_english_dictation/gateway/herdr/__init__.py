from __future__ import annotations
import json
import os
from pathlib import Path
import subprocess
import threading
from ...entity import Binding, VoiceError
from ..codex.transcript import find_rollout


class HerdrGateway:
    def __init__(self, binary: Path, history: Path | None = None):
        self.binary = binary
        self.history = history
        self.confirmed: dict[tuple[str, str, str], str] = {}
        self.lock = threading.Lock()

    def _call(self, pane: str, socket: str, args: list[str], expect_json: bool = True):
        env = dict(os.environ)
        env.update(HERDR_ENV='1', HERDR_PANE_ID=pane, HERDR_SOCKET_PATH=socket)
        try:
            result = subprocess.run([str(self.binary), *args], env=env,
                                    capture_output=True, text=True, timeout=8)
        except (subprocess.TimeoutExpired, OSError):
            raise VoiceError('Herdr не отвечает; операция не повторяется автоматически') from None
        if result.returncode:
            raise VoiceError('Herdr отклонил операцию: проверь, что целевая панель открыта')
        if len(result.stdout) > 256000:
            raise VoiceError('Herdr вернул слишком большой ответ')
        if not expect_json:
            return result.stdout
        try:
            return json.loads(result.stdout)
        except ValueError:
            raise VoiceError('Некорректный ответ Herdr') from None

    def inspect(self, pane: str, socket: str) -> Binding:
        reply = self._call(pane, socket, ['pane', 'get', pane])
        p = reply.get('result', {}).get('pane', {})
        if p.get('pane_id') != pane or not p.get('terminal_id'):
            raise VoiceError('Herdr не подтвердил целевую панель')
        session = p.get('agent_session') or {}
        identity = session.get('value') if session.get('kind') == 'id' and session.get('agent') == 'codex' else None
        session_error = None
        if p.get('agent') == 'codex' and self.history is not None:
            # Shared Codex app-server hooks may inherit another pane's environment.
            # Resolve from this pane's committed prompt instead of trusting that hook.
            try:
                rendered = self._call(pane, socket, ['pane', 'read', pane, '--source',
                                      'detection'], expect_json=False)
                identity = self._session_from_prompt(rendered)
                key = pane, socket, p['terminal_id']
                with self.lock:
                    if identity:
                        if len(self.confirmed) >= 32:
                            self.confirmed.clear()
                        self.confirmed[key] = identity
                    elif sum(line.startswith('› ') for line in rendered.splitlines()) < 2:
                        previous = self.confirmed.get(key)
                        if previous and self._completed_reply_visible(previous, rendered):
                            identity = previous
            except VoiceError as error:
                identity, session_error = None, str(error)
        return Binding(pane, socket, p['terminal_id'], identity, p.get('agent'), session_error)

    def _completed_reply_visible(self, session: str, rendered: str) -> bool:
        """Reconfirm a known session without scrolling a long reply's prompt back."""
        try:
            path = find_rollout(self.history.parent / 'sessions', session)
            if path is None:
                return False
            rows = self._last_rows(path)
        except (OSError, ValueError):
            return False
        for row in reversed(rows):
            try:
                record = json.loads(row)
            except (ValueError, UnicodeDecodeError):
                continue
            payload = record.get('payload') if isinstance(record, dict) else None
            if (record.get('type') if isinstance(record, dict) else None) != 'event_msg' or not isinstance(payload, dict):
                continue
            if payload.get('type') == 'task_started':
                return False  # A newer turn has not finished; an older reply proves nothing.
            if payload.get('type') == 'task_complete':
                text = payload.get('last_agent_message')
                if not isinstance(text, str):
                    return False
                # Ignore Markdown decoration and terminal soft wraps in both views.
                expected = ''.join(c for c in text if c.isalnum())[-160:]
                visible = ''.join(c for c in rendered if c.isalnum())
                return len(expected) >= 80 and expected in visible
        return False

    @staticmethod
    def _last_rows(path: Path) -> list[bytes]:
        with path.open('rb') as stream:
            stream.seek(0, 2)
            length = stream.tell()
            stream.seek(max(0, length - 256000))
            if length > 256000:
                stream.readline()
            return stream.read(256000).splitlines()

    def _session_from_prompt(self, rendered: str) -> str | None:
        lines = rendered.splitlines()
        starts = [i for i, line in enumerate(lines) if line.startswith('› ')]
        # Codex's last › block is the editable composer, never a submitted turn.
        if len(starts) < 2:
            return None
        begin, end = starts[-2], starts[-1]
        parts = [lines[begin][2:]]
        for line in lines[begin + 1:end]:
            if line and not line.startswith('  '):
                break
            parts.append(line.strip())
        prompt = ''.join(''.join(parts).split())
        if not prompt:
            return None
        try:
            rows = self._last_rows(self.history)
        except OSError:
            raise VoiceError('История Codex недоступна; привязка озвучки не подтверждена') from None
        matches = set()
        for row in rows:
            try:
                item = json.loads(row)
            except (ValueError, UnicodeDecodeError):
                continue
            if not isinstance(item, dict) or not isinstance(item.get('text'), str):
                continue
            session = item.get('session_id')
            if (''.join(item['text'].split()) == prompt and isinstance(session, str)
                    and session and len(session) <= 64
                    and all(c in '0123456789abcdef-' for c in session.lower())):
                matches.add(session)
        if len(matches) > 1:
            raise VoiceError('Одинаковый запрос найден в разных сессиях; озвучка не привязана')
        return next(iter(matches), None)

    def insert(self, binding: Binding, text: str) -> None:
        current = self.inspect(binding.pane, binding.socket)
        if current.terminal != binding.terminal or (binding.agent == 'codex' and current.session != binding.session):
            raise VoiceError('Целевая панель или сессия изменилась; текст не вставлен')
        self._call(binding.pane, binding.socket, ['pane', 'send-text', binding.pane, text], expect_json=False)
