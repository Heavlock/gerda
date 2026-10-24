from __future__ import annotations

import subprocess
import tempfile
import wave
from contextlib import contextmanager
from pathlib import Path

import imageio_ffmpeg


SUPPORTED_EXTENSIONS = {
    ".aac",
    ".flac",
    ".m4a",
    ".mkv",
    ".mov",
    ".mp3",
    ".mp4",
    ".mpeg",
    ".mpg",
    ".ogg",
    ".wav",
    ".webm",
}


def discover_inputs(path: Path) -> list[Path]:
    if path.is_file():
        return [path]
    if not path.exists():
        raise FileNotFoundError(f"Input path does not exist: {path}")
    return sorted(
        candidate
        for candidate in path.iterdir()
        if candidate.is_file()
        and candidate.suffix.lower() in SUPPORTED_EXTENSIONS
    )


def extract_audio(input_path: Path, temp_dir: Path) -> Path:
    audio_path = temp_dir / f"{input_path.stem}.wav"
    command = [
        imageio_ffmpeg.get_ffmpeg_exe(),
        "-y",
        "-i",
        str(input_path),
        "-vn",
        "-ac",
        "1",
        "-ar",
        "16000",
        "-c:a",
        "pcm_s16le",
        str(audio_path),
    ]
    subprocess.run(
        command,
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return audio_path


def wav_duration(audio_path: Path) -> float:
    with wave.open(str(audio_path), "rb") as audio:
        return audio.getnframes() / audio.getframerate()


class MediaGateway:
    def discover(self, path: Path) -> list[Path]:
        return discover_inputs(path)

    @contextmanager
    def prepare_audio(self, source: Path):
        with tempfile.TemporaryDirectory(prefix="transcribe-") as directory_name:
            audio_path = extract_audio(source, Path(directory_name))
            yield audio_path

    def duration(self, audio_path: Path) -> float:
        return wav_duration(audio_path)


__all__ = [
    "MediaGateway",
    "SUPPORTED_EXTENSIONS",
    "discover_inputs",
    "extract_audio",
    "wav_duration",
]
