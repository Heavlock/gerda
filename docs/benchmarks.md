# Recorded speech-generation comparison

Measured on 16 October 2026 with VibeVoice Realtime 0.5B, the Emma preset,
FP32/SDPA, five diffusion steps and CFG 1.5. Hardware: NVIDIA RTX 3060, 12 GB VRAM;
CPU: AMD Ryzen 9 9950X (16 cores / 32 threads). PyTorch CUDA runtime 12.6. The selected profile is in
[english-voice.json](../configs/english-voice.json).

For the same text producing 27.33 seconds of audio:

| Device | CPU threads | Median generation time |
| --- | ---: | ---: |
| CPU | 8 | 36.893 s |
| RTX 3060 | 2 host threads | 5.659 s |

That is a **6.52× reduction in generation time** in this experiment. CUDA with
four or eight host threads took 5.720 s and 5.698 s respectively; extra threads
did not improve this sample.

These are medians of two timed runs per configuration after warmup. The model,
voice, text, seed and quality settings were held constant. GPU-to-CPU audio
transfer and final CUDA synchronization were included. Downloads, model loading,
Codex's answer generation and speaker playback were excluded.

The [original timing CSV](benchmarks/tts-cpu-gpu-2026-10-16.csv) includes the short
sample, timing ranges and first-PCM measurements. First PCM is an internal audio
chunk, not a measured microphone-to-speaker latency.

This was a small local experiment, not a broad hardware benchmark. It does not
measure Whisper recognition or compare end-to-end latency with native Codex voice.
Moving Whisper to GPU also felt faster in daily use, but no matched CPU/GPU ASR
benchmark was recorded. The historical benchmark harness and audio are not
included in this source release; the CSV preserves the measurements, not a
one-command reproduction.
