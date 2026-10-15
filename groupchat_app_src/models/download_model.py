"""Download the pinned GGUF model with resume support and SHA-256 validation."""
import hashlib
from pathlib import Path
import shutil
import time
import urllib.request

FILENAME = 'Llama-3.2-3B-Instruct-Q4_K_M.gguf'
REVISION = '5ab33fa94d1d04e903623ae72c95d1696f09f9e8'
SHA256 = '6c1a2b41161032677be168d354123594c0e6e67d2b9227c84f296ad037c728ff'
SIZE = 2019377696
URL = f'https://huggingface.co/bartowski/Llama-3.2-3B-Instruct-GGUF/resolve/{REVISION}/{FILENAME}'
TARGET = Path(__file__).resolve().parent / FILENAME
PART = TARGET.with_suffix('.gguf.part')


def validate(path):
    if path.stat().st_size != SIZE:
        raise RuntimeError('Model size does not match the pinned file.')
    digest = hashlib.sha256()
    with path.open('rb') as source:
        for chunk in iter(lambda: source.read(8 * 1024 * 1024), b''):
            digest.update(chunk)
    if digest.hexdigest() != SHA256:
        raise RuntimeError('SHA-256 mismatch; model will not be used.')


def main():
    if TARGET.exists():
        validate(TARGET)
        print('Existing model SHA-256 verified.', flush=True)
        return
    offset = PART.stat().st_size if PART.exists() else 0
    if shutil.disk_usage(TARGET.parent).free < SIZE - offset + 100_000_000:
        raise RuntimeError('Insufficient free space for the model.')
    request = urllib.request.Request(URL, headers={'Range': f'bytes={offset}-'} if offset else {})
    if offset < SIZE:
        with urllib.request.urlopen(request, timeout=120) as response:
            if offset and response.status != 206:
                offset = 0
            if response.status == 206 and not response.headers.get('Content-Range', '').startswith(f'bytes {offset}-'):
                raise RuntimeError('Unexpected range response.')
            with PART.open('ab' if offset else 'wb') as output:
                total = offset
                last = time.monotonic()
                while chunk := response.read(4 * 1024 * 1024):
                    output.write(chunk)
                    total += len(chunk)
                    if time.monotonic() - last >= 10:
                        print(f'Downloaded {total / 1e9:.2f}/{SIZE / 1e9:.2f} GB ({total / SIZE:.0%})', flush=True)
                        last = time.monotonic()
    print('Checking SHA-256...', flush=True)
    validate(PART)
    PART.replace(TARGET)
    print(f'Model ready: {FILENAME}; SHA-256 verified.', flush=True)


if __name__ == '__main__':
    main()
