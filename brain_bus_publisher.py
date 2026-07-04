"""brain_bus_publisher.py — vinny-stack → the-brain live event wiring.

Usage:
    from brain_bus_publisher import publish_module_event, publish_pipeline_run

    run_id = publish_pipeline_run("started", modules_to_run=["capture","ocr","memory"])
    publish_module_event("ocr", "ocr_completed", detail="12 pages", outcome="pass", run_id=run_id)
    publish_pipeline_run("completed", run_id=run_id, summary="25 files processed")
"""
from __future__ import annotations
import json, os, sys, uuid
from datetime import datetime, timezone
from pathlib import Path

_SOURCE = "vinny-stack"
_REPO_ROOT = Path(__file__).resolve().parent

MODULES = [
    "capture", "ocr", "memory", "cache", "orchestrate", "infer",
    "export", "dashboard", "watch", "classify", "summarize",
    "search", "dedup", "backup", "sync", "notify", "route",
    "evaluate", "learn", "audit", "recover", "schedule",
    "transform", "publish", "oversee",
]

def _get_brain():
    candidates = [
        _REPO_ROOT.parent / "the-brain",
        Path.home() / "the-brain",
        Path.home() / "repos" / "the-brain",
    ]
    env_path = os.environ.get("BRAIN_REPO_PATH", "")
    if env_path:
        candidates.insert(0, Path(env_path))
    for c in candidates:
        if (c / "brain_sync.py").exists():
            if str(c) not in sys.path:
                sys.path.insert(0, str(c))
            try:
                from brain_sync import BrainSync
                return BrainSync()
            except Exception as e:
                print(f"[vinny-stack brain_bus] import error: {e}")
                return None
    print("[vinny-stack brain_bus] WARNING: the-brain not found. Set BRAIN_REPO_PATH.")
    return None

_brain = None
_brain_resolved = False

def _client():
    global _brain, _brain_resolved
    if not _brain_resolved:
        _brain = _get_brain()
        _brain_resolved = True
    return _brain

def publish_module_event(
    module_name: str, event_type: str, detail: str = "",
    outcome: str = "pass", run_id: str | None = None,
    metadata: dict | None = None,
) -> bool:
    rid = run_id or f"vs_{module_name}_{uuid.uuid4().hex[:8]}"
    brain = _client()
    if brain is None:
        return False
    detail_full = f"{detail} | {json.dumps(metadata)}" if metadata else detail
    try:
        ok = brain.learn(
            run_id=rid, source=_SOURCE, category=f"module:{module_name}",
            event_type=event_type, detail=detail_full, outcome=outcome,
        )
        brain.kg_add_node(
            node_id=f"module:{module_name}", node_type="module", label=module_name,
            properties={"stack": _SOURCE, "last_run": datetime.now(timezone.utc).isoformat()},
        )
        brain.kg_add_edge(
            source_id=_SOURCE, target_id=f"module:{module_name}",
            relation="contains", weight=1.0,
        )
        return ok
    except Exception as e:
        print(f"[vinny-stack brain_bus] error: {e}")
        return False

def publish_pipeline_run(
    status: str, modules_to_run: list | None = None,
    run_id: str | None = None, summary: str = "",
) -> str:
    rid = run_id or f"vs_run_{uuid.uuid4().hex[:12]}"
    detail = summary or f"modules={modules_to_run or 'all'}"
    brain = _client()
    if brain:
        try:
            brain.learn(
                run_id=rid, source=_SOURCE, category="pipeline",
                event_type=f"pipeline_{status}", detail=detail,
                outcome="pass" if status in ("started", "completed") else "error",
            )
        except Exception as e:
            print(f"[vinny-stack brain_bus] pipeline error: {e}")
    return rid

def publish_inference_result(
    model: str, prompt_tokens: int, completion_tokens: int,
    latency_ms: float, outcome: str = "pass", run_id: str | None = None,
) -> bool:
    return publish_module_event(
        "infer", "inference_completed",
        detail=f"model={model} prompt_tokens={prompt_tokens} completion_tokens={completion_tokens} latency_ms={latency_ms:.0f}",
        outcome=outcome, run_id=run_id,
        metadata={"model": model, "total_tokens": prompt_tokens + completion_tokens, "latency_ms": latency_ms},
    )

def publish_export_event(
    export_format: str, destination: str, record_count: int,
    outcome: str = "pass", run_id: str | None = None,
) -> bool:
    return publish_module_event(
        "export", "export_completed",
        detail=f"format={export_format} dest={destination} records={record_count}",
        outcome=outcome, run_id=run_id,
    )
