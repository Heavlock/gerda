"""One long-lived Emma process; resource settings never reach the caller."""
from __future__ import annotations
import argparse
import copy
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--runtime', type=Path, required=True)
    args = parser.parse_args()
    root, runtime = args.root, args.runtime
    profile = json.loads((root / 'configs/english-voice.json').read_text())
    if profile['voice'] != 'en-Emma_woman.pt':
        raise ValueError('Voice profile does not belong to Emma')
    output = sys.stdout
    sys.stdout = sys.stderr
    def emit(value):
        output.write(json.dumps(value) + '\n')
        output.flush()
    model_dir = root / 'models/vibevoice-realtime'
    voice = root / 'models/vibevoice-source/demo/voices/streaming_model' / profile['voice']
    for path, expected in [(model_dir / 'model.safetensors', profile['model_weight_sha256']),
                           (voice, profile['voice_sha256'])]:
        with path.open('rb') as stream:
            if hashlib.file_digest(stream, 'sha256').hexdigest() != expected:
                raise ValueError('Pinned voice/model digest mismatch')
    import torch
    device = 'cuda' if torch.cuda.is_available() else 'cpu'
    count = profile['cuda_host_threads'] if device == 'cuda' else profile['cpu_threads']
    cpus = sorted(os.sched_getaffinity(0))[:count]
    os.sched_setaffinity(0, cpus)
    for key in ['OMP_NUM_THREADS', 'MKL_NUM_THREADS', 'OPENBLAS_NUM_THREADS']:
        os.environ[key] = str(len(cpus))
    torch.set_num_threads(len(cpus))
    torch.set_num_interop_threads(profile['interop_threads'])
    torch.backends.cuda.matmul.allow_tf32 = False
    torch.backends.cudnn.allow_tf32 = False
    torch.backends.cudnn.benchmark = False
    if device == 'cuda':
        torch.cuda.set_per_process_memory_fraction(profile['cuda_memory_fraction'])
    from transformers.cache_utils import DynamicCache
    from transformers.modeling_outputs import BaseModelOutputWithPast
    from transformers.utils import logging
    from vibevoice.modular.modeling_vibevoice_streaming_inference import VibeVoiceStreamingForConditionalGenerationInference
    from vibevoice.modular.modular_vibevoice_text_tokenizer import VibeVoiceTextTokenizerFast
    from vibevoice.processor.vibevoice_streaming_processor import VibeVoiceStreamingProcessor
    from vibevoice.processor.vibevoice_tokenizer_processor import VibeVoiceTokenizerProcessor
    logging.set_verbosity_error()
    tokenizer = VibeVoiceTextTokenizerFast.from_pretrained(str(root / 'models/vibevoice-tokenizer'), local_files_only=True)
    processor = VibeVoiceStreamingProcessor(tokenizer=tokenizer, audio_processor=VibeVoiceTokenizerProcessor(),
                                             speech_tok_compress_ratio=3200, db_normalize=True)
    started = time.monotonic()
    model = VibeVoiceStreamingForConditionalGenerationInference.from_pretrained(
        str(model_dir), torch_dtype=torch.float32, device_map=device,
        attn_implementation='sdpa', local_files_only=True).eval()
    model.set_ddpm_inference_steps(num_steps=profile['ddpm_steps'])
    with torch.serialization.safe_globals([BaseModelOutputWithPast, DynamicCache]):
        prompt = torch.load(voice, map_location=device, weights_only=True)
    emit({'event': 'ready', 'device': device, 'threads': torch.get_num_threads(),
          'affinity': sorted(os.sched_getaffinity(0)), 'pid': os.getpid(),
          'load_seconds': time.monotonic() - started, 'voice': profile['voice']})

    while True:
        line = sys.stdin.buffer.readline(131073)
        if not line:
            break
        if len(line) > 131072 or not line.endswith(b'\n'):
            raise ValueError('Voice request exceeds limit')
        request = json.loads(line)
        identifier = request['id']
        if not re.fullmatch('[a-f0-9]{32}', identifier):
            raise ValueError('Invalid voice request identity')
        text = request['text']
        if not isinstance(text, str) or len(text) > 20000:
            raise ValueError('Voice text exceeds limit')
        cancel = runtime / ('cancel-' + identifier)
        dry_run = bool(request.get('dry_run', False))
        audio_lock = Path(request['audio_lock'])
        lock = None
        player = None
        generated = 0
        first_pcm = None
        start = time.monotonic()
        def stopped():
            return cancel.exists() or time.monotonic() - start > 7200
        try:
            if not dry_run:
                audio_lock.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
                lock = audio_lock.open('a')
                while not stopped():
                    try:
                        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                        break
                    except BlockingIOError:
                        time.sleep(0.1)
                if stopped():
                    emit({'event': 'done', 'id': identifier, 'cancelled': True})
                    continue
                player = subprocess.Popen(['pw-play', '--raw', '--rate', '24000', '--channels', '1',
                                           '--format', 'f32', '--latency', '100ms', '-'],
                                          stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
                                          stderr=sys.stderr, pass_fds=(lock.fileno(),))

            class Stream:
                def put(self, audio_chunks, sample_indices):
                    nonlocal generated, first_pcm
                    pcm = audio_chunks.detach().float().cpu().numpy().reshape(-1)
                    if first_pcm is None:
                        first_pcm = time.monotonic() - start
                    generated += len(pcm)
                    if player is not None and not stopped():
                        player.stdin.write(pcm.astype('<f4', copy=False).tobytes())
                        player.stdin.flush()
                def end(self, sample_indices=None):
                    pass

            # Keep sentences intact; cap each model call independently of response length.
            parts = re.split(r'(?<=[.!?])\s+|\n+', text)
            chunks = []
            current = ''
            for part in parts:
                while len(part) > 700:
                    cut = part.rfind(' ', 0, 700)
                    cut = cut if cut > 0 else 700
                    if current:
                        chunks.append(current)
                        current = ''
                    chunks.append(part[:cut])
                    part = part[cut:].strip()
                if len(current) + len(part) > 700:
                    chunks.append(current)
                    current = ''
                current = (current + ' ' + part).strip()
            if current:
                chunks.append(current)
            torch.manual_seed(42)
            with torch.no_grad():
                for chunk in chunks:
                    if stopped():
                        break
                    inputs = processor.process_input_with_cached_prompt(text=chunk, cached_prompt=prompt,
                                 padding=True, return_tensors='pt', return_attention_mask=True)
                    inputs = {k: v.to(device) if torch.is_tensor(v) else v for k, v in inputs.items()}
                    result = model.generate(**inputs, max_new_tokens=1200, cfg_scale=profile['cfg_scale'],
                            tokenizer=processor.tokenizer, generation_config={'do_sample': False},
                            show_progress_bar=False, verbose=False, all_prefilled_outputs=copy.deepcopy(prompt),
                            audio_streamer=Stream(), stop_check_fn=stopped)
                    if result.reach_max_step_sample is not None and bool(result.reach_max_step_sample.any()):
                        raise RuntimeError('Voice segment exceeded generation limit')
            if player:
                if stopped():
                    player.terminate()
                else:
                    player.stdin.close()
                player.wait(timeout=10)
                if player.returncode and not stopped():
                    raise RuntimeError('PipeWire playback failed')
            emit({'event': 'done', 'id': identifier, 'cancelled': stopped(), 'device': device,
                  'audio_seconds': generated / 24000, 'seconds': time.monotonic() - start,
                  'first_pcm_seconds': first_pcm, 'pid': os.getpid()})
        except Exception as error:
            emit({'event': 'error', 'id': identifier, 'error': type(error).__name__})
        finally:
            if player and player.poll() is None:
                player.terminate()
                try:
                    player.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    player.kill()
                    player.wait(timeout=2)
            if lock:
                lock.close()
            cancel.unlink(missing_ok=True)


if __name__ == '__main__':
    main()
