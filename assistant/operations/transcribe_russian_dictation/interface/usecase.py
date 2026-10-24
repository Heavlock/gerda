from __future__ import annotations

from typing import Protocol
from ..entity import Input, Result


class Usecase(Protocol):
    def execute(self, value: Input) -> Result: ...
