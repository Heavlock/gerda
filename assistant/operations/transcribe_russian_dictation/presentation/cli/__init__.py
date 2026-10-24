from __future__ import annotations

import re

from ...entity import Input
from ...interface.usecase import Usecase


class Handler:
    def __init__(self, usecase: Usecase) -> None:
        self.usecase = usecase

    def execute(self, capture: str) -> str:
        if not re.fullmatch(r'[A-Za-z0-9_-]{1,64}', capture):
            raise ValueError('Invalid Russian recording token')
        return self.usecase.execute(Input(capture)).text
