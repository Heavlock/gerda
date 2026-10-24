from __future__ import annotations
from dataclasses import dataclass
import json
from pathlib import Path


@dataclass
class NextTurn:
    turn: str | None = None
    final: str = ''
    finished: bool = False
    aborted: bool = False

    @staticmethod
    def identity(record: dict) -> str | None:
        p = record.get('payload', {})
        if not isinstance(p, dict):
            return None
        metadata = record.get('metadata') or {}
        retained = metadata.get('retained_source') or {}
        retained = retained.get('id') or {}
        passthrough = p.get('internal_chat_message_metadata_passthrough') or {}
        if not isinstance(retained, dict) or not isinstance(passthrough, dict):
            return None
        identity = p.get('turn_id') or retained.get('turn_id') or passthrough.get('turn_id')
        return identity if isinstance(identity, str) else None

    def feed(self, record: dict) -> str | None:
        if self.finished:
            return None
        p = record.get('payload', {})
        if not isinstance(p, dict):
            return None
        typ = record.get('type')
        turn = self.identity(record)
        if typ == 'response_item' and p.get('type') == 'message' and p.get('role') == 'user':
            if self.turn is None and turn:
                self.turn = turn
            return None
        if self.turn is None or turn != self.turn:
            return None
        if typ == 'response_item' and p.get('type') == 'message' and p.get('role') == 'assistant' and p.get('phase') == 'final_answer':
            self.final = '\n'.join(c.get('text', '') for c in p.get('content', [])
                                   if c.get('type') in {'output_text', 'text'})[:65536]
        if typ == 'event_msg' and p.get('type') == 'turn_aborted':
            self.finished = self.aborted = True
        if typ == 'event_msg' and p.get('type') == 'task_complete':
            self.finished = True
            text = p.get('last_agent_message') or self.final
            return text[:65536] if isinstance(text, str) and text.strip() else None
        return None


class Tail:
    """Read only complete new JSONL records, with bounded line and batch sizes."""
    def __init__(self, path: Path, offset: int):
        self.path = path
        self.offset = offset
        stat = path.stat()
        self.identity = stat.st_dev, stat.st_ino
        self.discarding = False

    def read(self) -> list[dict]:
        stat = self.path.stat()
        if (stat.st_dev, stat.st_ino) != self.identity or stat.st_size < self.offset:
            raise ValueError('Codex history changed')
        records = []
        with self.path.open('rb') as stream:
            stream.seek(self.offset)
            for _ in range(32):
                before = stream.tell()
                line = stream.readline(1024 * 1024 + 1)
                if not line:
                    break
                if not line.endswith(b'\n'):
                    if len(line) > 1024 * 1024:
                        self.discarding = True
                        self.offset = stream.tell()
                        continue
                    stream.seek(before)
                    break
                self.offset = stream.tell()
                if self.discarding:
                    self.discarding = False
                    continue
                try:
                    item = json.loads(line)
                except (ValueError, UnicodeDecodeError):
                    continue
                if isinstance(item, dict):
                    records.append(item)
        return records


def find_rollout(root: Path, session: str) -> Path | None:
    if not session or any(c not in '0123456789abcdef-' for c in session.lower()) or len(session) > 64:
        raise ValueError('Invalid Codex session identity')
    files = list(root.glob(f'*/*/*/*{session}.jsonl'))
    if len(files) != 1:
        return None
    path = files[0]
    with path.open('rb') as stream:
        line = stream.readline(1024 * 1024)
    meta = json.loads(line)
    if meta.get('type') != 'session_meta' or meta.get('payload', {}).get('id') != session:
        raise ValueError('Codex history identity mismatch')
    return path
