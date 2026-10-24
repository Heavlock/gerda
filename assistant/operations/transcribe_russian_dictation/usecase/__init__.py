from __future__ import annotations

from ..entity import Input, RecognitionError, Result
from ..interface.gateway import Recognizer


class TranscribeRussianDictation:
    def __init__(self, recognizer: Recognizer) -> None:
        self.recognizer = recognizer

    def execute(self, value: Input) -> Result:
        duration = self.recognizer.duration(value.capture)
        if duration < 0.1:
            raise RecognitionError('Запись слишком короткая')
        text = self.recognizer.recognize(value.capture, with_vad=duration > 20)
        text = ' '.join(text.split())
        if len(text) > 16000:
            raise RecognitionError('Слишком длинная запись; текст не вставлен')
        return Result(text)
