"""modules/01_capture.py  —  vinny-stack CAPTURE stage

Ingest raw input from:
  - Local file path (any MIME type)
  - URL (fetched with requests, text extracted)
  - Clipboard text (macOS pbpaste)
  - Raw string passed directly via artifact['raw_text']

Outputs:
  artifact['raw_text']    : str  — extracted text content
  artifact['mime_type']   : str  — detected MIME type
  artifact['source_type'] : str  — 'file' | 'url' | 'clipboard' | 'raw'
  artifact['source_path'] : str  — original path or URL
"""
from __future__ import annotations

import mimetypes
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from _brain_client import emit_stage


def _detect_mime(path: str) -> str:
    mime, _ = mimetypes.guess_type(path)
    return mime or "application/octet-stream"


def _read_file(path: str) -> tuple[str, str]:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"capture: file not found: {path}")
    mime = _detect_mime(path)
    if mime and mime.startswith("text/"):
        return p.read_text(errors="replace"), mime
    if mime in ("application/json", "application/yaml", "application/toml"):
        return p.read_text(errors="replace"), mime
    # Binary — return placeholder; OCR stage handles images/PDFs
    return f"[binary:{mime}:{p.stat().st_size}bytes]", mime


def _fetch_url(url: str) -> tuple[str, str]:
    try:
        import requests
        r = requests.get(url, timeout=30, headers={"User-Agent": "vinny-stack/1.0"})
        r.raise_for_status()
        ct = r.headers.get("content-type", "text/html")
        mime = ct.split(";")[0].strip()
        # Strip HTML tags crudely for now; extract stage refines later
        text = r.text
        if "html" in mime:
            import re
            text = re.sub(r"<[^>]+>", " ", text)
            text = re.sub(r"\s+", " ", text).strip()
        return text[:50_000], mime  # cap at 50k chars
    except Exception as e:
        raise RuntimeError(f"capture: URL fetch failed for {url}: {e}")


def _read_clipboard() -> str:
    try:
        result = subprocess.run(["pbpaste"], capture_output=True, text=True, timeout=5)
        return result.stdout or ""
    except Exception as e:
        raise RuntimeError(f"capture: clipboard read failed: {e}")


def run(artifact: Dict[str, Any], run_id: str = "") -> Dict[str, Any]:
    """
    CAPTURE stage entry point.

    Reads from artifact['input_path']:
      - 'clipboard'        → reads macOS clipboard
      - URL (http/https)   → fetches and strips HTML
      - file path          → reads text content
    Or passes through artifact['raw_text'] if already set.
    """
    input_path = artifact.get("input_path", "")
    raw_text   = artifact.get("raw_text", "")

    source_type = "raw"
    mime_type   = "text/plain"

    try:
        if raw_text:
            source_type = "raw"
        elif input_path == "clipboard":
            raw_text   = _read_clipboard()
            source_type = "clipboard"
        elif input_path.startswith(("http://", "https://")):
            raw_text, mime_type = _fetch_url(input_path)
            source_type = "url"
        elif input_path:
            raw_text, mime_type = _read_file(input_path)
            source_type = "file"
        else:
            raise ValueError("capture: no input_path or raw_text provided")

        artifact.update({
            "raw_text":    raw_text,
            "mime_type":   mime_type,
            "source_type": source_type,
            "source_path": input_path,
        })

        emit_stage(
            run_id=run_id, stage_name="capture", outcome="pass",
            detail=f"source_type={source_type} mime={mime_type} chars={len(raw_text)}",
        )
        print(f"  [capture] ✓ source={source_type} mime={mime_type} chars={len(raw_text)}")

    except Exception as exc:
        emit_stage(run_id=run_id, stage_name="capture", outcome="fail", detail=str(exc)[:200])
        raise

    return artifact
