from __future__ import annotations
from typing import Callable
from ...entity import Input
from ...interface.usecase import Usecase


class Handler:
    def __init__(self, usecase: Usecase, notify: Callable[[str], None]):
        self.usecase = usecase
        self.notify = notify

    def execute(self, pane: str, socket: str, terminal: str, session: str, turn: str, text: str) -> None:
        if not all(isinstance(x, str) and x for x in [pane, socket, terminal, session, turn, text]):
            return
        result = self.usecase.execute(Input(pane, socket, terminal, session, turn, text))
        if result.status == 'language':
            self.notify('Codex ответил не по-английски; английская озвучка пропущена')
