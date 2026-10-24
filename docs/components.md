# Component sources

Gerda connects existing models; it does not train or fine-tune them.
Dependencies and downloaded models retain their own licenses and usage terms.

| Component | Source | Role |
| --- | --- | --- |
| Herdr | https://herdr.dev/ | Terminal panes and command bindings |
| faster-whisper | https://github.com/SYSTRAN/faster-whisper | English recognition through CTranslate2 |
| Whisper medium.en | https://huggingface.co/Systran/faster-whisper-medium.en | English recognition weights |
| VibeVoice | https://github.com/microsoft/VibeVoice | Speech synthesis implementation and Emma preset |
| VibeVoice Realtime 0.5B | https://huggingface.co/microsoft/VibeVoice-Realtime-0.5B | Speech synthesis weights |
| Qwen2.5-0.5B | https://huggingface.co/Qwen/Qwen2.5-0.5B | Tokenizer assets used by VibeVoice |
| onnx-asr | https://github.com/istupakov/onnx-asr | Russian GigaAM and Silero VAD runtime |
| PipeWire | https://pipewire.org/ | Audio capture and playback |

Exact English model/source revisions are in `scripts/install-english-models.py`
and `configs/english-voice.json`. Python packages are pinned in
`requirements-english.txt` and `requirements.txt`. The VibeVoice model and Emma
preset are checked against SHA-256 digests. Downloads go to ignored directories;
no third-party model weights or voice recordings are committed here.
