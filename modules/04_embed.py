"""modules/04_embed.py  —  vinny-stack stage 04: EMBED

Generates local vector embeddings for each chunk.

Backend priority:
  1. llama-cpp-python (GGUF embedding model, fully local)
  2. HTTP embedding server (LM Studio / Ollama /v1/embeddings endpoint)
  3. Hash fingerprint fallback (deterministic 64-dim vector from SHA256)
     — pipeline never hard-fails; downstream stages get a vector either way

Artifact inputs:
  chunks      list[dict]  From chunk stage

Artifact outputs (added to each chunk dict):
  vector      list[float]  Embedding vector
  embed_model str          Name of model used
  embed_dim   int          Vector dimensionality

Artifact-level outputs:
  embed_model str
  embed_dim   int
  embed_backend str        'llama_cpp' | 'http' | 'hash_fallback'

Config:
  VINNY_LLM_BASE        HTTP embedding server base URL
  VINNY_EMBED_MODEL     Model name (for HTTP backend)
  VINNY_EMBED_GGUF_PATH Path to .gguf embedding model file (llama-cpp)
"""
from __future__ import annotations

import hashlib
import math
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _brain_client import emit_stage  # noqa: E402

LLM_BASE    = os.environ.get('VINNY_LLM_BASE',    'http://localhost:1234/v1')
EMBED_MODEL = os.environ.get('VINNY_EMBED_MODEL', 'nomic-embed-text')
GGUF_PATH   = os.environ.get('VINNY_EMBED_GGUF_PATH', '')


# ---------------------------------------------------------------------------
# Backend implementations
# ---------------------------------------------------------------------------

def _embed_llama_cpp(texts: List[str], gguf_path: str) -> Optional[List[List[float]]]:
    try:
        from llama_cpp import Llama  # type: ignore
        llm = Llama(model_path=gguf_path, embedding=True, verbose=False, n_ctx=512)
        return [llm.embed(t) for t in texts]
    except Exception as e:
        print(f'    [embed] llama_cpp backend failed: {e}')
        return None


def _embed_http(texts: List[str], base_url: str, model: str) -> Optional[List[List[float]]]:
    try:
        import requests  # type: ignore
        resp = requests.post(
            f'{base_url.rstrip("/")}/embeddings',
            json={'model': model, 'input': texts},
            timeout=60,
        )
        resp.raise_for_status()
        data = resp.json()
        # OpenAI-compatible response
        items = sorted(data['data'], key=lambda x: x['index'])
        return [item['embedding'] for item in items]
    except Exception as e:
        print(f'    [embed] HTTP backend failed: {e}')
        return None


def _embed_hash_fallback(texts: List[str], dim: int = 64) -> List[List[float]]:
    """
    Deterministic pseudo-embedding from SHA256.  Not semantically meaningful
    but keeps the pipeline running and lets dedup/store stages work.
    Each output dimension is a float in [-1, 1] derived from the hash bytes.
    """
    results = []
    for text in texts:
        digest = hashlib.sha256(text.encode('utf-8')).digest()  # 32 bytes
        # Tile to fill dim dimensions
        raw = (digest * math.ceil(dim / len(digest)))[:dim]
        vector = [(b / 127.5) - 1.0 for b in raw]
        results.append(vector)
    return results


# ---------------------------------------------------------------------------
# Batch helper (embed in batches to avoid server timeouts)
# ---------------------------------------------------------------------------

def _batch_embed(
    texts:    List[str],
    batch_sz: int = 32,
    gguf_path: str = '',
    llm_base:  str = LLM_BASE,
    model:     str = EMBED_MODEL,
) -> tuple[List[List[float]], str, int]:
    """
    Returns (vectors, backend_name, dim).
    Tries backends in priority order; falls back to hash if all fail.
    """
    all_vectors: List[List[float]] = []
    backend = 'unknown'
    dim = 0

    for i in range(0, len(texts), batch_sz):
        batch = texts[i:i + batch_sz]
        vecs: Optional[List[List[float]]] = None

        if gguf_path and Path(gguf_path).exists():
            vecs = _embed_llama_cpp(batch, gguf_path)
            if vecs:
                backend = 'llama_cpp'

        if vecs is None:
            vecs = _embed_http(batch, llm_base, model)
            if vecs:
                backend = 'http'

        if vecs is None:
            vecs = _embed_hash_fallback(batch)
            backend = 'hash_fallback'

        all_vectors.extend(vecs)

    dim = len(all_vectors[0]) if all_vectors else 0
    return all_vectors, backend, dim


# ---------------------------------------------------------------------------
# run()
# ---------------------------------------------------------------------------

def run(artifact: Dict[str, Any], run_id: str = '') -> Dict[str, Any]:
    outcome = 'pass'
    detail  = ''

    try:
        chunks: List[Dict[str, Any]] = artifact.get('chunks', [])

        if not chunks:
            detail = 'no chunks to embed — skipped'
            print(f'    {detail}')
            artifact['embed_backend'] = 'skipped'
            emit_stage(run_id=run_id, stage_name='embed', outcome='pass', detail=detail)
            return artifact

        texts = [c['text'] for c in chunks]
        gguf  = artifact.get('embed_gguf_path', GGUF_PATH)
        base  = artifact.get('llm_base', LLM_BASE)
        model = artifact.get('embed_model', EMBED_MODEL)

        vectors, backend, dim = _batch_embed(
            texts, gguf_path=gguf, llm_base=base, model=model
        )

        # Attach vectors back to each chunk
        for chunk, vec in zip(chunks, vectors):
            chunk['vector']      = vec
            chunk['embed_model'] = model if backend != 'hash_fallback' else 'sha256_hash'

        artifact['chunks']        = chunks
        artifact['embed_model']   = model if backend != 'hash_fallback' else 'sha256_hash'
        artifact['embed_dim']     = dim
        artifact['embed_backend'] = backend

        detail = f'n_chunks={len(chunks)} backend={backend} dim={dim} model={model}'
        print(f'    {detail}')

    except Exception as exc:
        outcome = 'fail'
        detail  = str(exc)[:200]
        artifact['embed_error'] = detail
        print(f'    ERROR: {exc}')

    emit_stage(
        run_id=run_id, stage_name='embed', outcome=outcome,
        detail=detail, model=artifact.get('embed_model', ''),
    )
    return artifact
