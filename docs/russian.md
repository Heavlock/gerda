# Russian F8 dictation

Russian dictation uses GigaAM v3 E2E RNN-T INT8 on CPU. It has a separate virtual
environment and does not require the English installation or a GPU.
Use the Linux, PipeWire, Herdr and uv prerequisites from the main README.

From the repository root:

```bash
uv venv --python 3.11 .venv
uv pip install --python .venv/bin/python -r requirements.txt
mkdir -p models/gigaam-v3-e2e-rnnt models/silero-vad
.venv/bin/python - <<'PY'
import onnx_asr
onnx_asr.load_model(
    'gigaam-v3-e2e-rnnt', 'models/gigaam-v3-e2e-rnnt',
    quantization='int8', providers=['CPUExecutionProvider'])
onnx_asr.load_vad(
    'silero', 'models/silero-vad', providers=['CPUExecutionProvider'])
PY
.venv/bin/python -m assistant.russian_daemon --check
.venv/bin/python scripts/activate-russian-dictation.py
```

The installer creates the user service and `~/.local/bin/herdr-dictate` launcher.
It does **not** add a keybinding. Add the F8 entry from [Herdr setup](herdr.md),
then run `herdr server reload-config`.

Press F8, speak Russian, and press F8 again. Review the inserted text and submit
it manually. The first press starts recording and starts the worker loading its
model. The worker stays warm for subsequent recordings, then exits after five
minutes of inactivity. It is started on demand, not enabled at login.

Recordings longer than 20 seconds use Silero VAD to split the captured audio for
recognition. This does not make a pause end the recording: stopping is still manual.
The temporary audio is removed after successful recognition and insertion.

```bash
systemctl --user status gerda-russian.service
journalctl --user -u gerda-russian.service -n 30
systemctl --user stop gerda-russian.service
```

The worker uses two CPU threads by default. The service environment defines
`GERDA_RUSSIAN_THREADS` and `GERDA_RUSSIAN_IDLE_SECONDS`. Change them with a systemd
user override if needed. Russian dictation and English capture coordinate through
a shared microphone lock.
