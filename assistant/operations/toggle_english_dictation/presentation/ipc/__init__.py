from __future__ import annotations
import re
from ...entity import Input, Result
from ...interface.usecase import Usecase


class Handler:
    def __init__(self, usecase: Usecase):
        self.usecase = usecase

    def execute(self, request: dict) -> Result:
        if set(request) != {'mode', 'pane', 'socket'}:
            raise ValueError('Invalid hotkey request')
        if request['mode'] not in {'dictate', 'speak'}:
            raise ValueError('Invalid English mode')
        if not isinstance(request['pane'], str) or not re.fullmatch(r'[a-zA-Z0-9:_-]{1,128}', request['pane']):
            raise ValueError('Herdr did not supply a valid pane')
        if not isinstance(request['socket'], str) or not request['socket'].startswith('/') or len(request['socket']) > 200:
            raise ValueError('Invalid Herdr socket')
        return self.usecase.execute(Input(**request))
