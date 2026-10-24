from typing import Protocol


class Pane(Protocol):
    def matches(self, pane: str, socket: str, terminal: str, session: str) -> bool: ...


class Speech(Protocol):
    def submit(self, pane: str, socket: str, terminal: str, session: str,
               turn: str, text: str) -> None: ...
