"""modules/18_store.py  —  vinny-stack STORE stage

Persist the artifact and its metadata to the-brain (brain.db) via the
harmony bus. Also writes a local JSON record to VINNY_STORE_DIR for
offline / audit access.

Outputs:
  artifact['brain_record_id']   : str   — run_id used as brain record key
  artifact['stored_at']         : str   — ISO timestamp
  artifact['store_path']        : str   — local JSON file path

Environment:
  VINNY_STORE_DIR   default ~/.vinny/store/
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from _brain_client import emit_stage, get_bus

STORE_DIR = Path(os.environ.get("VINNY_STORE_DIR", Path.home() / ".vinny" / "store"))


def _safe_artifact(artifact: Dict[str, Any]) -> Dict[str, Any]:
    """Strip vectors (large + not JSON-serialisable as floats list cleanly) for storage."""
    safe = {k: v for k, v in artifact.items() if k != "vectors"}
    if artifact.get("vectors"):
        safe["embed_dim"]    = artifact.get("embed_dim", 0)
        safe["vector_count"] = len(artifact["vectors"])
    if artifact.get("chunks"):
        safe["chunk_count"]  = len(artifact["chunks"])
        safe["chunks_stored"] = False  # full chunks not duplicated in store
        del safe["chunks"]
    return safe


def run(artifact: Dict[str, Any], run_id: str = "") -> Dict[str, Any]:
    stored_at = datetime.now(timezone.utc).isoformat()
    record_id = run_id or artifact.get("run_id", "unknown")

    safe = _safe_artifact(artifact)
    safe["stored_at"] = stored_at
    safe["run_id"]    = record_id

    try:
        # ── Local JSON record ──────────────────────────────────────────────
        STORE_DIR.mkdir(parents=True, exist_ok=True)
        store_path = STORE_DIR / f"{record_id}.json"
        store_path.write_text(json.dumps(safe, indent=2, ensure_ascii=False))

        # ── Brain bus: publish learn event with summary ──────────────────────
        bus = get_bus()
        if bus:
            source     = artifact.get("source_path", "")[:120]
            mime       = artifact.get("mime_type", "")
            n_chunks   = artifact.get("chunk_count", 0)
            n_vectors  = len(artifact.get("vectors", []))
            embed_dim  = artifact.get("embed_dim", 0)

            try:
                bus.publish_learn(
                    run_id     = record_id,
                    source     = "vinny-stack",
                    category   = "pipeline_store",
                    event_type = "GATE_PASSED",
                    detail     = (
                        f"source={source} mime={mime} "
                        f"chunks={n_chunks} vectors={n_vectors} dim={embed_dim}"
                    ),
                    outcome    = "pass",
                )
            except Exception:
                pass  # bus failure never blocks store

        artifact.update({
            "brain_record_id": record_id,
            "stored_at":       stored_at,
            "store_path":      str(store_path),
        })

        emit_stage(
            run_id=run_id, stage_name="store", outcome="pass",
            detail=f"path={store_path} record_id={record_id}",
        )
        print(f"  [store] ✓ record_id={record_id} path={store_path}")

    except Exception as exc:
        emit_stage(run_id=run_id, stage_name="store", outcome="fail", detail=str(exc)[:200])
        raise

    return artifact
