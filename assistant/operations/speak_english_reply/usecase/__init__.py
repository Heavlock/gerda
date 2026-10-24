from __future__ import annotations
import re
from ..entity import Input, Result
from ..interface.gateway import Pane, Speech


def spoken_text(text: str) -> str:
    text = re.sub(r'(?ms)^\s*(```|~~~).*?^\s*\1[^\n]*(?:\n|$)', ' Code is shown in the terminal. ', text)
    text = re.sub(r'(?ms)^\s*(```|~~~).*$', ' Code is shown in the terminal. ', text)
    text = re.sub(r'!\[[^\]]*\]\([^)]*\)', ' ', text)
    text = re.sub(r'\[([^\]]+)\]\([^)]*\)', r'\1', text)
    text = re.sub(r'https?://\S+', ' ', text)
    text = re.sub(r'`[^`\n]+`', lambda m: ' code ' if '/' in m[0] or '\\' in m[0] else m[0].strip('`'), text)
    text = re.sub(r'(?m)^\s{0,3}(?:#{1,6}\s+|>\s*|[-*+]\s+|\d+[.)]\s+)', '', text)
    text = text.replace('**', '').replace('__', '').replace('|', ', ')
    text = re.sub(r'(?<!\w)(?:/[\w.-]+){2,}(?::\d+)?', ' file path ', text)
    return re.sub(r'\s+', ' ', text).strip()[:20000]


class SpeakEnglishReply:
    def __init__(self, pane: Pane, speech: Speech):
        self.pane = pane
        self.speech = speech

    def execute(self, value: Input) -> Result:
        if not value.session or not value.turn or not self.pane.matches(
                value.pane, value.socket, value.terminal, value.session):
            return Result('unavailable')
        text = spoken_text(value.text[:65536])
        if not text:
            return Result('empty')
        if len(re.findall('[А-Яа-яЁё]', text)) > max(4, len(re.findall('[A-Za-z]', text)) // 5):
            return Result('language')
        self.speech.submit(value.pane, value.socket, value.terminal, value.session, value.turn, text)
        return Result('queued')
