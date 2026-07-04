"""modules/03_chunk.py  —  vinny-stack CHUNK stage

Split artifact['raw_text'] into semantic chunks suitable for embedding.
Strategy: sentence-aware sliding window with configurable size + overlap.

Outputs:
  artifact['chunks']       : list[str]   — text chunks
  artifact['chunk_count']  : int
  artifact['chunk_size']   : int         — target chars per chunk
  artifact['chunk_overlap']: int         — overlap chars between chunks

Environment:
  VINNY_CHUNK_SIZE    default 800  (chars)
  VINNY_CHUNK_OVERLAP default 100  (chars)
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path
from typing import Any, Dict, List

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from _brain_client import emit_stage

CHUNK_SIZE    = int(os.environ.get("VINNY_CHUNK_SIZE",    "800"))
CHUNK_OVERLAP = int(os.environ.get("VINNY_CHUNK_OVERLAP", "100"))


def _sentence_split(text: str) -> List[str]:
    """Split on sentence boundaries: . ! ? followed by whitespace."""
    parts = re.split(r"(?<=[.!?])\s+", text.strip())
    return [p.strip() for p in parts if p.strip()]


def _chunk_sentences(sentences: List[str], size: int, overlap: int) -> List[str]:
    """Greedily pack sentences into chunks of ~`size` chars with `overlap` carry-over."""
    chunks: List[str] = []
    current = ""
    carry   = ""  # overlap text from previous chunk

    for sent in sentences:
        candidate = (carry + " " + current + " " + sent).strip() if current else (carry + " " + sent).strip()
        if len(candidate) > size and current:
            # Flush current chunk
            chunk_text = (carry + " " + current).strip()
            chunks.append(chunk_text)
            # Carry-over: last `overlap` chars of flushed chunk
            carry   = chunk_text[-overlap:] if overlap else ""
            current = sent
        else:
            current = candidate

    if current.strip():
        chunks.append((carry + " " + current).strip())

    return [c for c in chunks if c]


def run(artifact: Dict[str, Any], run_id: str = "") -> Dict[str, Any]:
    raw_text = artifact.get("raw_text", "")
    if not raw_text:
        emit_stage(run_id=run_id, stage_name="chunk", outcome="fail",
                   detail="raw_text empty — capture stage must run first")
        raise ValueError("chunk: raw_text is empty")

    size    = int(artifact.get("chunk_size",    CHUNK_SIZE))
    overlap = int(artifact.get("chunk_overlap", CHUNK_OVERLAP))

    try:
        sentences = _sentence_split(raw_text)
        chunks    = _chunk_sentences(sentences, size, overlap)

        if not chunks:
            chunks = [raw_text[:size]]  # fallback: single chunk

        artifact.update({
            "chunks":        chunks,
            "chunk_count":   len(chunks),
            "chunk_size":    size,
            "chunk_overlap": overlap,
        })

        emit_stage(
            run_id=run_id, stage_name="chunk", outcome="pass",
            detail=f"n_chunks={len(chunks)} size={size} overlap={overlap}",
        )
        print(f"  [chunk] ✓ {len(chunks)} chunks (size={size} overlap={overlap})")

    except Exception as exc:
        emit_stage(run_id=run_id, stage_name="chunk", outcome="fail", detail=str(exc)[:200])
        raise

    return artifact
