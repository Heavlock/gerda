"""Provision the pinned English voice runtime without changing the Russian env."""
from __future__ import annotations
import argparse
import concurrent.futures
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import urllib.request


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--temp',type=Path,required=True)
    parser.add_argument('--python',default=sys.executable,help='Python 3.11 interpreter for the English environment')
    args=parser.parse_args()
    root=Path(__file__).resolve().parents[1];temp=args.temp.resolve();temp.mkdir(parents=True,exist_ok=True)
    env=dict(os.environ);env.update(TMPDIR=str(temp),UV_CACHE_DIR=str(temp/'uv-cache'),XDG_CACHE_HOME=str(temp/'cache'),HF_HUB_CACHE=str(temp/'hf-cache'),HF_ASSETS_CACHE=str(temp/'hf-assets'),HF_HUB_DISABLE_XET='1',HF_TOKEN_PATH=str(Path.home()/'.cache/huggingface/token'),UV_CONCURRENT_DOWNLOADS='4')
    uv=shutil.which('uv');hf=shutil.which('hf')
    if not uv or not hf:
        parser.error('Install uv and the Hugging Face hf CLI first; see README.md')
    subprocess.run([args.python,'-c','import sys; assert sys.version_info[:2] == (3, 11), "The pinned runtime requires Python 3.11"'],check=True)
    rev='16fb2cb1217c9934a886e1948ffb06120caa2df5';source=root/'models/vibevoice-source'
    def download(repo,revision,files,dest):
        subprocess.run([hf,'download',repo,*files,'--revision',revision,'--local-dir',str(dest),'--max-workers','2'],env=env,check=True)
    def source_files():
        tree=json.load(urllib.request.urlopen(f'https://api.github.com/repos/microsoft/VibeVoice/git/trees/{rev}?recursive=1',timeout=60))
        files=[v['path'] for v in tree['tree'] if v['type']=='blob' and (v['path'].startswith('vibevoice/') or v['path'] in ['pyproject.toml','README.md','LICENSE','demo/voices/streaming_model/en-Emma_woman.pt'])]
        def get(name):
            p=source/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(urllib.request.urlopen(f'https://raw.githubusercontent.com/microsoft/VibeVoice/{rev}/{name}',timeout=60).read())
        with concurrent.futures.ThreadPoolExecutor(4) as pool:list(pool.map(get,files))
    def environment():
        if not (root/'.venv-english/bin/python').exists():
            subprocess.run([uv,'venv','--python',args.python,str(root/'.venv-english')],env=env,check=True)
        subprocess.run([uv,'pip','install','--python',str(root/'.venv-english/bin/python'),'-r',str(root/'requirements-english.txt')],env=env,check=True)
    jobs=[(source_files,()),(environment,()),(download,('microsoft/VibeVoice-Realtime-0.5B','6bce5f06044837fe6d2c5d7a71a84f0416bd57e4',['config.json','preprocessor_config.json','model.safetensors'],root/'models/vibevoice-realtime')),(download,('Systran/faster-whisper-medium.en','a29b04bd15381511a9af671baec01072039215e3',['config.json','model.bin','tokenizer.json','vocabulary.txt'],root/'models/whisper-medium.en')),(download,('Qwen/Qwen2.5-0.5B','060db6499f32faf8b98477b0a26969ef7d8b9987',['tokenizer.json','tokenizer_config.json','vocab.json','merges.txt'],root/'models/vibevoice-tokenizer'))]
    with concurrent.futures.ThreadPoolExecutor(5) as pool:
        futures=[pool.submit(fn,*a) for fn,a in jobs]
        for f in futures:f.result()
    subprocess.run([uv,'pip','install','--python',str(root/'.venv-english/bin/python'),'--no-deps',str(source)],env=env,check=True)
    for p,expected in [(root/'models/vibevoice-realtime/model.safetensors','7758b150b8139deb48ac1ff6f181f745c8fedd5511232fd974b3eb217d83b514'),(source/'demo/voices/streaming_model/en-Emma_woman.pt','75b15c481e0d848991f1789620aa9929c583ec2c5f701f8152362cf74498bbf8')]:
        with p.open('rb') as f:
            if hashlib.file_digest(f,'sha256').hexdigest()!=expected:
                raise RuntimeError('Downloaded file checksum mismatch: '+p.name)
    print('ENGLISH RUNTIME INSTALLED',flush=True)

if __name__=='__main__':main()
