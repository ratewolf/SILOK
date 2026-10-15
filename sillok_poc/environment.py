"""Write non-secret runtime metadata without importing the GPU stack."""
from datetime import datetime, timezone
import importlib.metadata
import json
import platform
from pathlib import Path
import sqlite3
import subprocess
import sys

PACKAGES = ['lxml', 'pytest', 'torch', 'triton', 'unsloth', 'unsloth_zoo',
            'torchvision', 'xformers', 'transformers', 'peft', 'bitsandbytes', 'accelerate',
            'huggingface-hub', 'tokenizers', 'safetensors', 'numpy']


def snapshot():
    packages = {}
    for package in PACKAGES:
        try:
            packages[package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            packages[package] = None
    try:
        gpu = subprocess.run(['nvidia-smi', '--query-gpu=name,memory.total,driver_version',
                              '--format=csv,noheader'], capture_output=True, text=True,
                             timeout=10, check=True).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        gpu = None
    return dict(captured_at=datetime.now(timezone.utc).isoformat(), python=sys.version,
                platform=platform.platform(), sqlite=sqlite3.sqlite_version,
                packages=packages, gpu=gpu)


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', default='reports/environment.json')
    args = parser.parse_args()
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(snapshot(), ensure_ascii=False, indent=2) + '\n')
    print(output)
