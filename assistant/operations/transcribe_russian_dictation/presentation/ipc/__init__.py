from __future__ import annotations

from dataclasses import asdict
import re

from ...entity import Input, RecognitionError
from ...interface.usecase import Usecase


class Handler:
    def __init__(self, usecase: Usecase) -> None:
        self.usecase = usecase

    def execute(self, body: dict) -> dict:
        if set(body) != {'capture'} or not isinstance(body['capture'], str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,64}', body['capture']):
            raise ValueError('Invalid Russian recording token')
        try:
            return asdict(self.usecase.execute(Input(body['capture'])))
        except RecognitionError as error:
            return {'error': str(error)}
