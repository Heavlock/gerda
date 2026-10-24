from __future__ import annotations
from ..entity import Input, Recording, Result, VoiceError
from ..interface.gateway import Capture, Herdr, Recognizer, Replies, Speech
from ..interface.repository import Repository


class ToggleEnglishDictation:
    def __init__(self, repository: Repository, capture: Capture, recognizer: Recognizer,
                 herdr: Herdr, replies: Replies, speech: Speech):
        self.repository = repository
        self.capture = capture
        self.recognizer = recognizer
        self.herdr = herdr
        self.replies = replies
        self.speech = speech

    def execute(self, value: Input) -> Result:
        if not self.repository.acquire():
            return Result('busy', 'Предыдущая голосовая операция ещё выполняется')
        try:
            active = self.repository.get()
            if active is not None:
                if active.mode != value.mode:
                    key = 'F6' if active.mode == 'speak' else 'F7'
                    return Result('busy', f'Идёт запись: заверши её клавишей {key}')
                # Always use the saved pane, even if focus moved before stop.
                registration = None
                try:
                    self.capture.stop(active.capture)
                    text = self.recognizer.transcribe(active.capture).strip()
                    if not text:
                        return Result('empty', 'Речь не распознана')
                    if len(text) > 16000:
                        raise VoiceError('Слишком длинная запись; текст не вставлен')
                    current = self.herdr.inspect(active.binding.pane, active.binding.socket)
                    if current.terminal != active.binding.terminal:
                        raise VoiceError('Целевая панель была заменена; текст не вставлен')
                    if active.mode == 'speak':
                        if current.session_error:
                            raise VoiceError(current.session_error)
                        if current.agent != 'codex' or (active.binding.session and
                                                       current.session != active.binding.session):
                            raise VoiceError('Сессия Codex изменилась; текст не вставлен')
                        text += '\n\nPlease reply in English.'
                        registration = self.replies.arm(current)
                    try:
                        self.herdr.insert(current, text)
                        if registration:
                            self.replies.commit(registration)
                    except Exception:
                        if registration:
                            self.replies.revoke(registration)
                        raise
                    return Result('inserted', 'Английский текст вставлен в сохранённую панель — проверь и нажми Enter')
                finally:
                    self.repository.save(None)
                    self.capture.finish(active.capture)
            binding = self.herdr.inspect(value.pane, value.socket)
            if value.mode == 'speak' and binding.session_error:
                raise VoiceError(binding.session_error)
            if value.mode == 'speak' and binding.agent != 'codex':
                raise VoiceError('F6 работает в панели Codex; для обычного терминала используй F7')
            self.replies.cancel(value.pane, value.socket)
            self.speech.cancel()
            if value.mode == 'speak':
                self.speech.prewarm()
            capture = self.capture.start()
            try:
                self.repository.save(Recording(capture, value.mode, binding))
            except Exception:
                self.capture.finish(capture)
                raise
            key = 'F6' if value.mode == 'speak' else 'F7'
            return Result('recording', f'Запись английской речи — нажми {key} для завершения')
        except VoiceError as error:
            return Result('error', str(error))
        finally:
            self.repository.release()
