from __future__ import annotations

from pathlib import Path
import subprocess
import time

from assistant.technical.voiceipc import request
from ...entity import Input, RecognitionError, Result


class RemoteUsecase:
    """Client for the operation hosted in the on-demand Russian worker."""

    def __init__(self, socket: Path, *, startup_timeout: float = 20) -> None:
        self.socket = socket
        self.startup_timeout = startup_timeout

    def execute(self, value: Input) -> Result:
        try:
            subprocess.run(['systemctl', '--user', 'start', 'gerda-russian.service'],
                           check=True, timeout=self.startup_timeout,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            deadline = time.monotonic() + self.startup_timeout
            while True:
                try:
                    reply = request(self.socket, {'capture': value.capture}, response_limit=131072)
                    break
                except (FileNotFoundError, ConnectionRefusedError):
                    # Retry only failed connects, never a request already submitted.
                    if time.monotonic() >= deadline:
                        raise RecognitionError('Русское распознавание не успело запуститься') from None
                    subprocess.run(['systemctl', '--user', 'start', 'gerda-russian.service'],
                                   check=True, timeout=max(0.1, deadline - time.monotonic()),
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    time.sleep(0.05)
            if set(reply) == {'error'} and isinstance(reply['error'], str):
                raise RecognitionError(reply['error'])
            if set(reply) != {'text'} or not isinstance(reply['text'], str) or len(reply['text']) > 16000:
                raise RecognitionError('Русское распознавание вернуло ошибку; проверь журнал gerda-russian')
            return Result(reply['text'])
        except RecognitionError:
            raise
        except (OSError, ValueError, subprocess.SubprocessError) as error:
            raise RecognitionError('Русское распознавание недоступно; проверь gerda-russian.service') from error
