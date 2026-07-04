"""modules/01_capture.py  —  vinny-stack stage 01: CAPTURE

Ingests raw input from:
  - Local file path (text, image, PDF, any binary)
  - HTTP/HTTPS URL (downloads with requests)
  - Clipboard text (macOS pbpaste / pyperclip)
  - Stdin (piped input)
  - Raw string passed directly in artifact['input_path']

Outputs artifact fields:
  raw_bytes   bytes       Raw content of the input
  raw_text    str | None  Decoded text (if UTF-8 decodable)
  mime        str         Detected MIME type
  source_type str         'file' | 'url' | 'clipboard' | 'stdin' | 'raw'
  source_path str         Original input path/URL
  filename    str         Basename of the source
  size_bytes  int         Byte length of raw_bytes
"""
from __future__ import annotations

import mimetypes
import os
import sys
from pathlib import Path
from typing import Any, Dict

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _brain_client import emit_stage  # noqa: E402


# ---------------------------------------------------------------------------
# MIME detection
# ---------------------------------------------------------------------------

def _detect_mime(data: bytes, filename: str) -> str:
    mime, _ = mimetypes.guess_type(filename)
    if mime:
        return mime
    # Sniff first bytes
    sig = data[:8]
    if sig[:4] == b'%PDF':
        return 'application/pdf'
    if sig[:8] == b'\x89PNG\r\n\x1a\n':
        return 'image/png'
    if sig[:2] in (b'\xff\xd8', ):
        return 'image/jpeg'
    if sig[:4] in (b'GIF8', ):
        return 'image/gif'
    if sig[:2] in (b'PK', ):
        return 'application/zip'
    try:
        data.decode('utf-8')
        return 'text/plain'
    except UnicodeDecodeError:
        return 'application/octet-stream'


# ---------------------------------------------------------------------------
# Source handlers
# ---------------------------------------------------------------------------

def _from_url(url: str) -> bytes:
    try:
        import requests  # type: ignore
        r = requests.get(url, timeout=30, headers={'User-Agent': 'vinny-stack/1.0'})
        r.raise_for_status()
        return r.content
    except Exception as e:
        raise RuntimeError(f'[capture] URL fetch failed: {e}') from e


def _from_clipboard() -> bytes:
    # Try macOS pbpaste first, then pyperclip
    try:
        import subprocess
        result = subprocess.run(['pbpaste'], capture_output=True, timeout=5)
        if result.returncode == 0:
            return result.stdout or result.stdout  # may be empty bytes
    except Exception:
        pass
    try:
        import pyperclip  # type: ignore
        return pyperclip.paste().encode('utf-8')
    except Exception as e:
        raise RuntimeError(f'[capture] Clipboard read failed: {e}') from e


def _from_stdin() -> bytes:
    if sys.stdin.isatty():
        raise RuntimeError('[capture] stdin requested but no piped input detected')
    return sys.stdin.buffer.read()


# ---------------------------------------------------------------------------
# Main run()
# ---------------------------------------------------------------------------

def run(artifact: Dict[str, Any], run_id: str = '') -> Dict[str, Any]:
    input_path: str = artifact.get('input_path', '')
    outcome = 'pass'
    detail = ''

    try:
        raw_bytes: bytes
        source_type: str
        filename: str

        if not input_path or input_path == '__clipboard__':
            raw_bytes = _from_clipboard()
            source_type = 'clipboard'
            filename = 'clipboard.txt'

        elif input_path == '__stdin__':
            raw_bytes = _from_stdin()
            source_type = 'stdin'
            filename = 'stdin.txt'

        elif input_path.startswith(('http://', 'https://')):
            raw_bytes = _from_url(input_path)
            source_type = 'url'
            # Derive filename from URL path
            from urllib.parse import urlparse
            parsed = urlparse(input_path)
            filename = Path(parsed.path).name or 'downloaded'
            if '.' not in filename:
                filename += '.html'

        elif Path(input_path).exists():
            raw_bytes = Path(input_path).read_bytes()
            source_type = 'file'
            filename = Path(input_path).name

        else:
            # Treat as raw string content
            raw_bytes = input_path.encode('utf-8')
            source_type = 'raw'
            filename = 'raw_input.txt'

        mime = _detect_mime(raw_bytes, filename)

        # Attempt text decode
        raw_text: str | None = None
        if mime.startswith('text/') or mime == 'application/json':
            try:
                raw_text = raw_bytes.decode('utf-8')
            except UnicodeDecodeError:
                pass

        artifact.update({
            'raw_bytes':   raw_bytes,
            'raw_text':    raw_text,
            'mime':        mime,
            'source_type': source_type,
            'source_path': input_path,
            'filename':    filename,
            'size_bytes':  len(raw_bytes),
        })

        detail = f'source={source_type} mime={mime} size={len(raw_bytes)}'
        print(f'    source={source_type} filename={filename} mime={mime} size={len(raw_bytes):,}b')

    except Exception as exc:
        outcome = 'fail'
        detail = str(exc)[:200]
        artifact['capture_error'] = detail
        print(f'    ERROR: {exc}')

    emit_stage(run_id=run_id, stage_name='capture', outcome=outcome, detail=detail)
    return artifact
