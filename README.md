# Gerda

Local voice dictation and spoken Codex replies for [Herdr](https://herdr.dev/).
Speak, take a pause, stop recording when you are ready, then review the text before sending it.

| Key | Action | Recognition / voice |
| --- | --- | --- |
| **F7** | English dictation | faster-whisper `medium.en` |
| **F6** | English dictation, then read the next completed Codex answer aloud | Whisper + VibeVoice Realtime 0.5B / Emma |
| **F8** | Russian dictation, installed separately | GigaAM v3 E2E RNN-T INT8 |

Press the same key again to stop recording. **Enter is always yours to press.**
F6 appends `Please reply in English.` to the visible prompt. F7 and F8 also work
in ordinary terminal panes; F6 needs Codex.

English dictation remembers the pane where recording started. Moving focus does
not redirect the transcript. F7 cancels a pending spoken reply in that pane;
starting a new English recording interrupts English playback.

This release contains the key-operated modes above and a separate batch
transcriber. It does not include the older wake-word listener or tray interface.
Some runtime notifications are still in Russian.

## Requirements

- Linux x86-64 with glibc 2.28 or newer, Python **3.11**, and a systemd user session.
- PipeWire, a working microphone and audio output.
- Herdr installed and running locally. Integration was checked with **Herdr 0.9.3**.
- Codex running inside a Herdr pane for F6, with readable local session history.
- Internet access for the initial dependency and model downloads.

An NVIDIA GPU is useful for English recognition and speech generation. The
recorded tests used an RTX 3060 with 12 GB VRAM. Whisper uses CUDA when available
and retries on CPU if GPU recognition fails. Emma uses CPU when CUDA is unavailable;
CPU speech generation was slower than playback in the recorded test.
The pinned English environment installs CUDA libraries even on a CPU-only machine.
Allow several GB for model files and several more for the Python environment.

Speech recognition and synthesis run locally after installation. Codex still uses
its own model service. F6 reads Codex's local history format; future Codex or Herdr
changes may require adapter updates.

## Install English dictation and speech

Run these commands from a normal terminal on the machine with your microphone.
Keep the checkout at a permanent path: the installed service points to it.

On Ubuntu, install the small system tools first:

```bash
sudo apt update
sudo apt install git curl pipewire-bin libnotify-bin libsndfile1 util-linux
```

Install [uv](https://docs.astral.sh/uv/getting-started/installation/) if needed:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
export PATH="$HOME/.local/bin:$PATH"
uv python install 3.11
uv tool install --python 3.11 'huggingface-hub==0.36.2'
```

Install [Herdr](https://herdr.dev/docs/install/) if needed:

```bash
curl -fsSL https://herdr.dev/install.sh | sh
herdr --version
```

Start Herdr in a separate terminal and finish its initial setup. If you are already
inside a Herdr pane, keep using that session; do not launch a nested Herdr.

Download Gerda and its pinned English models:

```bash
git clone https://github.com/Heavlock/gerda.git
cd gerda
GERDA_DOWNLOAD_DIR="$(mktemp -d -t gerda-download.XXXXXXXX)"
uv run --python 3.11 --no-project python scripts/install-english-models.py \
  --temp "$GERDA_DOWNLOAD_DIR"
```

The installer creates `.venv-english/` and downloads Whisper, VibeVoice, its
tokenizer and the Emma preset into `models/`. The temporary directory contains
download/build caches and can be removed after a successful installation.
Model weights are not stored in this Git repository.

Check that the models load, then activate the service and keys:

```bash
.venv-english/bin/python -m assistant.daemon --check
.venv-english/bin/python scripts/activate-english-modes.py
```

The check loads both models without opening the microphone or playing audio.
Activation installs `~/.local/bin/gerda-english`, enables the user service, adds
F6/F7 to Herdr's config, and reloads that config. An existing config is backed up
as `config.toml.before-gerda-english`. Conflicting F6/F7 bindings are rejected
before changes are made. Existing F8 bindings are preserved.

For manual keys or an existing custom layout:

```bash
.venv-english/bin/python scripts/activate-english-modes.py --no-keybindings
```

Follow [Herdr integration and keybindings](docs/herdr.md), including custom
shortcuts, command types and alternate executable/config paths.

## Try it

1. Focus a Herdr pane and press **F7**.
2. Say: “Please explain this code in simple English.” Pause as long as you need.
3. Press **F7** again. The transcript appears after recognition finishes.
4. Review it and press **Enter**.
5. In a Codex pane, use **F6** the same way to hear the completed reply in English.

F6 waits for the final answer before generating speech. It does not read incoming
model tokens or progress updates. Code blocks, full URLs and file paths are
removed from the spoken version. Review remains useful: recognition can still
mishear words, and Emma can still mispronounce them.

## Optional Russian dictation and batch transcription

See [Russian F8 setup](docs/russian.md) and [batch audio/video transcription](docs/batch.md).
Russian recognition uses its own `.venv/` and CPU models. It is not required for F6/F7.

## Manage the service

```bash
systemctl --user status gerda-english.service
journalctl --user -u gerda-english.service -n 50
systemctl --user restart gerda-english.service
systemctl --user disable --now gerda-english.service
```

Whisper stays loaded between requests. The separate Emma process releases its
model after five minutes of inactivity; the English service remains available.
The speech profile is in [configs/english-voice.json](configs/english-voice.json).
The implementation currently supports the pinned Emma preset, not arbitrary voice files.

Troubleshooting and removal instructions are in [docs/herdr.md](docs/herdr.md).

## Development and measurements

The unit suite uses fake model and audio adapters. No downloads or GPU are required:

```bash
uv run --python 3.11 --no-project python -m unittest discover -s tests -v
bash -n scripts/herdr-dictate.sh
```

The tests cover recording control, literal text insertion, pane/session matching,
final-turn selection, fallback, IPC and installation bindings. They do not
replace a physical microphone/keybinding test on your machine.

The [recorded CPU/GPU comparison](docs/benchmarks.md) includes timing data and
its limits. The 6.52× result is **speech generation**, not Whisper recognition or
end-to-end Codex response time.

Third-party software and models retain their upstream terms. See
[component sources](docs/components.md).
