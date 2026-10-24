# Batch audio/video transcription

This is a separate Russian transcription command. It does not use Herdr,
hotkeys or Codex. Install the Python dependencies and download GigaAM and Silero
using [Russian setup](russian.md); service activation is unnecessary for batch use.

## Local Python

Put media files in `input/`, then run from the repository root:

```bash
mkdir -p input output
INPUT_PATH="$PWD/input" OUTPUT_DIR="$PWD/output" \
GIGAAM_MODEL_DIR="$PWD/models/gigaam-v3-e2e-rnnt" \
GIGAAM_VAD_MODEL_DIR="$PWD/models/silero-vad" \
  .venv/bin/python -m app.transcribe
```

Each input produces `.txt`, `.srt` and `.json` output. Supported extensions:
`mp4`, `mkv`, `mov`, `webm`, `mp3`, `wav`, `m4a`, `ogg`, `flac`, `aac`, `mpeg`, `mpg`.
The Python package `imageio-ffmpeg` supplies the ffmpeg executable.

## Docker alternative

With the same downloaded models and Docker Compose available:

```bash
mkdir -p input output
docker compose build
docker compose run --rm --user "$(id -u):$(id -g)" gigaam
```

The container mounts inputs and model files read-only. Outputs are written using
your host UID/GID. Docker is only needed for this alternative, not the hotkeys.

`GIGAAM_VAD=auto` applies speech segmentation above 20 seconds. Use `true` to
always segment or `false` to disable it. Other controls are listed in
[compose.yaml](../compose.yaml).
