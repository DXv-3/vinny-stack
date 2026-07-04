"""modules/04_embed.py  —  vinny-stack EMBED stage

Generate local vector embeddings for each chunk in artifact['chunks'].
Calls a local embedding endpoint (LM Studio, Ollama, llama.cpp server).

Outputs:
  artifact['vectors']      : list[list[float]]  — one vector per chunk
  artifact['embed_model']  : str                — model name used
  artifact['embed_dim']    : int                — vector dimension

Environment:
  VINNY_LLM_BASE      default http://localhost:1234/v1
  VINNY_EMBED_MODEL   default nomic-embed-text
  VINNY_EMBED_BATCH   default 8  (chunks per API call)

Fallback:
  If local embedding server is unreachable, stores empty vectors ([]) so
  downstream stages can detect and skip vector-dependent operations.
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from _brain_client import emit_stage

LLM_BASE    = os.environ.get("VINNY_LLM_BASE",    "http://localhost:1234/v1")
EMBED_MODEL = os.environ.get("VINNY_EMBED_MODEL", "nomic-embed-text")
EMBED_BATCH = int(os.environ.get("VINNY_EMBED_BATCH", "8"))


def _embed_batch(texts: List[str]) -> List[List[float]]:
    """Call the local /v1/embeddings endpoint for a batch of texts."""
    import requests
    payload = {"model": EMBED_MODEL, "input": texts}
    r = requests.post(
        f"{LLM_BASE}/embeddings",
        json=payload,
        timeout=60,
    )
    r.raise_for_status()
    data = r.json()["data"]
    # Sort by index to preserve order
    data.sort(key=lambda d: d["index"])
    return [d["embedding"] for d in data]


def run(artifact: Dict[str, Any], run_id: str = "") -> Dict[str, Any]:
    chunks = artifact.get("chunks", [])
    if not chunks:
        emit_stage(run_id=run_id, stage_name="embed", outcome="fail",
                   detail="chunks empty — chunk stage must run first")
        raise ValueError("embed: chunks list is empty")

    all_vectors: List[List[float]] = []
    embed_dim   = 0
    failed      = False

    try:
        t0 = time.time()
        for i in range(0, len(chunks), EMBED_BATCH):
            batch  = chunks[i : i + EMBED_BATCH]
            vecs   = _embed_batch(batch)
            all_vectors.extend(vecs)
        elapsed = time.time() - t0

        embed_dim = len(all_vectors[0]) if all_vectors else 0

        artifact.update({
            "vectors":     all_vectors,
            "embed_model": EMBED_MODEL,
            "embed_dim":   embed_dim,
        })

        emit_stage(
            run_id=run_id, stage_name="embed", outcome="pass",
            detail=f"n_vectors={len(all_vectors)} dim={embed_dim} model={EMBED_MODEL} elapsed={elapsed:.2f}s",
            model=EMBED_MODEL,
        )
        print(f"  [embed] ✓ {len(all_vectors)} vectors dim={embed_dim} ({elapsed:.2f}s)")

    except Exception as exc:
        # Graceful fallback: store empty vectors so pipeline continues
        failed = True
        all_vectors = [[] for _ in chunks]
        artifact.update({
            "vectors":     all_vectors,
            "embed_model": EMBED_MODEL,
            "embed_dim":   0,
            "embed_error": str(exc),
        })
        emit_stage(
            run_id=run_id, stage_name="embed", outcome="fail",
            detail=f"server unreachable, empty vectors stored: {str(exc)[:150]}",
            model=EMBED_MODEL,
        )
        print(f"  [embed] ⚠  embedding server unreachable — empty vectors stored ({exc})")
        # Don’t re-raise: downstream stages degrade gracefully on empty vectors

    return artifact
