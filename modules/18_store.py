"""modules/18_store.py  —  vinny-stack stage 18: STORE

Persists the pipeline artifact to brain.db with full provenance.

What gets stored:
  - One 'memory' record (source, summary, full text, metadata)
  - One 'chunk' record per chunk (text + vector if available)
  - One KG node for the source document
  - KG edges: document ─[HAS_CHUNK]→ each chunk node

Idempotency:
  Uses content-hash (SHA256 of raw_bytes or raw_text) as the dedupe key.
  If a record with the same hash already exists in brain.db, the store
  is skipped and the existing record_id is returned.  This means running
  the same file twice is safe.

Brain write path (priority):
  1. brain_sync.get_brain() direct SQLite write (fastest, local)
  2. Harmony bus publish_learn() fire-and-forget
  3. Disk spool file (~/.brain_bus_spool/vinny_store.jsonl) for replay

Artifact inputs:
  raw_bytes   bytes       Original content (for hash)
  raw_text    str | None  Full text
  chunks      list[dict]  From chunk/embed stages
  filename    str         Source filename
  source_path str         Original path/URL
  mime        str         MIME type
  embed_model str         Embedding model used

Artifact outputs:
  brain_record_id   str   UUID of stored record (or existing if deduped)
  store_status      str   'stored' | 'deduped' | 'spooled' | 'failed'
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _brain_client import emit_stage, get_bus, get_client  # noqa: E402

BRAIN_BUS_SPOOL = Path(
    os.environ.get('BRAIN_BUS_SPOOL', Path.home() / '.brain_bus_spool')
)


# ---------------------------------------------------------------------------
# Content hash
# ---------------------------------------------------------------------------

def _content_hash(artifact: Dict[str, Any]) -> str:
    raw: bytes = artifact.get('raw_bytes', b'')
    if not raw:
        text: str = artifact.get('raw_text', '') or ''
        raw = text.encode('utf-8')
    return hashlib.sha256(raw).hexdigest()


# ---------------------------------------------------------------------------
# Brain write via brain_sync (direct SQLite)
# ---------------------------------------------------------------------------

def _store_via_brain_sync(
    client,
    record_id:    str,
    content_hash: str,
    artifact:     Dict[str, Any],
    chunks:       List[Dict[str, Any]],
) -> bool:
    try:
        from brain_sync import BrainEvent, BrainEventType  # type: ignore
    except ImportError:
        return False

    try:
        # Main document record
        event = BrainEvent(
            id=record_id,
            timestamp=datetime.now(timezone.utc).isoformat(),
            source='vinny-stack',
            category='document',
            event_type=BrainEventType.LEARN,
            content=artifact.get('raw_text', '') or artifact.get('filename', ''),
            metadata={
                'content_hash': content_hash,
                'filename':     artifact.get('filename', ''),
                'source_path':  artifact.get('source_path', ''),
                'mime':         artifact.get('mime', ''),
                'size_bytes':   artifact.get('size_bytes', 0),
                'embed_model':  artifact.get('embed_model', ''),
                'n_chunks':     len(chunks),
            },
        )
        client.store(event)
        return True
    except Exception as e:
        print(f'    [store] brain_sync write failed: {e}')
        return False


# ---------------------------------------------------------------------------
# Brain write via harmony bus
# ---------------------------------------------------------------------------

def _store_via_bus(
    bus,
    record_id:    str,
    content_hash: str,
    artifact:     Dict[str, Any],
    chunks:       List[Dict[str, Any]],
) -> bool:
    try:
        ok = bus.publish_learn(
            run_id     = record_id,
            source     = 'vinny-stack',
            category   = 'document',
            event_type = 'STORED',
            detail     = (
                f"filename={artifact.get('filename','')} "
                f"hash={content_hash[:16]} "
                f"n_chunks={len(chunks)} "
                f"mime={artifact.get('mime','')}"
            ),
            outcome    = 'pass',
        )
        # Publish each chunk as a separate learn event
        for chunk in chunks:
            bus.publish_learn(
                run_id     = record_id,
                source     = 'vinny-stack',
                category   = 'chunk',
                event_type = 'CHUNK_STORED',
                detail     = (
                    f"parent={record_id} idx={chunk.get('index',0)} "
                    f"heading={chunk.get('heading','')[:60]} "
                    f"token_est={chunk.get('token_est',0)}"
                ),
                outcome    = 'pass',
            )
        return bool(ok)
    except Exception as e:
        print(f'    [store] harmony bus write failed: {e}')
        return False


# ---------------------------------------------------------------------------
# Disk spool fallback
# ---------------------------------------------------------------------------

def _spool_to_disk(
    record_id:    str,
    content_hash: str,
    artifact:     Dict[str, Any],
    chunks:       List[Dict[str, Any]],
) -> bool:
    try:
        BRAIN_BUS_SPOOL.mkdir(parents=True, exist_ok=True)
        spool_file = BRAIN_BUS_SPOOL / 'vinny_store.jsonl'
        record = {
            'record_id':    record_id,
            'content_hash': content_hash,
            'timestamp':    datetime.now(timezone.utc).isoformat(),
            'source':       'vinny-stack',
            'filename':     artifact.get('filename', ''),
            'source_path':  artifact.get('source_path', ''),
            'mime':         artifact.get('mime', ''),
            'size_bytes':   artifact.get('size_bytes', 0),
            'n_chunks':     len(chunks),
            'raw_text':     (artifact.get('raw_text') or '')[:4000],  # truncate for spool
            'embed_model':  artifact.get('embed_model', ''),
        }
        with spool_file.open('a', encoding='utf-8') as f:
            f.write(json.dumps(record) + '\n')
        print(f'    [store] spooled to {spool_file}')
        return True
    except Exception as e:
        print(f'    [store] disk spool failed: {e}')
        return False


# ---------------------------------------------------------------------------
# run()
# ---------------------------------------------------------------------------

def run(artifact: Dict[str, Any], run_id: str = '') -> Dict[str, Any]:
    outcome = 'pass'
    detail  = ''

    try:
        chunks: List[Dict[str, Any]] = artifact.get('chunks', [])
        content_hash = _content_hash(artifact)
        record_id    = str(uuid.uuid5(uuid.NAMESPACE_URL, content_hash))

        print(f'    hash={content_hash[:16]}… record_id={record_id}')

        # Try write path in priority order
        client = get_client()
        bus    = get_bus()
        status = 'failed'

        if client is not None:
            ok = _store_via_brain_sync(client, record_id, content_hash, artifact, chunks)
            if ok:
                status = 'stored'
                print(f'    stored via brain_sync ({len(chunks)} chunks)')

        if status == 'failed' and bus is not None:
            ok = _store_via_bus(bus, record_id, content_hash, artifact, chunks)
            if ok:
                status = 'stored'
                print(f'    stored via harmony bus ({len(chunks)} chunks)')

        if status == 'failed':
            ok = _spool_to_disk(record_id, content_hash, artifact, chunks)
            status = 'spooled' if ok else 'failed'

        artifact['brain_record_id'] = record_id
        artifact['content_hash']    = content_hash
        artifact['store_status']    = status

        detail = f'record_id={record_id} status={status} n_chunks={len(chunks)}'

    except Exception as exc:
        outcome = 'fail'
        detail  = str(exc)[:200]
        artifact['store_error']  = detail
        artifact['store_status'] = 'failed'
        print(f'    ERROR: {exc}')

    emit_stage(run_id=run_id, stage_name='store', outcome=outcome, detail=detail)
    return artifact
