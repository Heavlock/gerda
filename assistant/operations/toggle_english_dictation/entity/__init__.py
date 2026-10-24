from __future__ import annotations
from dataclasses import dataclass


@dataclass(frozen=True)
class Binding:
    pane: str
    socket: str
    terminal: str
    session: str | None
    agent: str | None
    session_error: str | None = None


@dataclass(frozen=True)
class Recording:
    capture: str
    mode: str
    binding: Binding


@dataclass(frozen=True)
class Input:
    mode: str
    pane: str
    socket: str


@dataclass(frozen=True)
class Result:
    status: str
    message: str


class VoiceError(Exception):
    pass
