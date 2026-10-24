from __future__ import annotations
from dataclasses import dataclass


@dataclass(frozen=True)
class Input:
    pane: str
    socket: str
    terminal: str
    session: str
    turn: str
    text: str


@dataclass(frozen=True)
class Result:
    status: str
