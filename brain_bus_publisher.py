"""brain_bus_publisher.py — vinny-stack → the-brain live event wiring.

Instruments all 25 vinny-stack modules. Each module calls publish_module_event().
The orchestrator calls publish_pipeline_run() at start/end of each full run.

Usage:
    from brain_bus_publisher import publish_module_event, publish_pipeline_run

    run_id = publish_pipeline_run("started", modules_to_run=["capture","ocr","memory"])
    publish_module_event("ocr", "ocr_completed", detail="12 pages", run_id=run_id)
    publish_pipeline_run("completed", run_id=run_id, summary="25 files processed")

Requires:
    Set BRAIN_SYNC_PATH env var to the directory containing brain_sync.py.
"""
from __future__ import annotations
import json, uuid
from datetime import datetime, timezone
from _brain_client import get_client

_SOURCE = "vinny-stack"

# Update these to match your actual module names
MODULES = [
    "capture", "ocr", "memory", "cache", "orchestrate", "infer",
    "export", "dashboard", "watch", "classify", "summarize",
    "search", "dedup", "backup", "sync", "notify", "route",
    "evaluate", "learn", "audit", "recover", "schedule",
    "transform", "publish", "oversee",
]

def publish_module_event(
    module_name: str,
    event_type: str,
    detail: str = "",
    outcome: str = "pass",
    run_id: str | None = None,
    metadata: dict | None = None,
) -> bool:
    """Publish an event from any of the 25 vinny-stack modules."""
    rid = run_id or f"vs_{module_name}_{uuid.uuid4().hex[:8]}"
    brain = get_client()
    if brain is None:
        return False
    detail_full = f"{detail} | {json.dumps(metadata)}" if metadata else detail
    try:
        ok = brain.learn(
            run_id=rid, source=_SOURCE,
            category=f"module:{module_name}",
            event_type=event_type,
            detail=detail_full, outcome=outcome,
        )
        brain.kg_add_node(
            node_id=f"module:{module_name}",
            node_type="module",
            label=module_name,
            properties={
                "stack": _SOURCE,
                "last_run": datetime.now(timezone.utc).isoformat(),
            },
        )
        brain.kg_add_edge(
            source_id=_SOURCE,
            target_id=f"module:{module_name}",
            relation="contains",
            weight=1.0,
        )
        return ok
    except Exception as e:
        print(f"[vinny-stack brain_bus] module event error: {e}")
        return False

def publish_pipeline_run(
    status: str,
    modules_to_run: list | None = None,
    run_id: str | None = None,
    summary: str = "",
) -> str:
    """Publish a pipeline-level run event. Returns run_id."""
    rid = run_id or f"vs_run_{uuid.uuid4().hex[:12]}"
    detail = summary or f"modules={modules_to_run or 'all'}"
    brain = get_client()
    if brain:
        try:
            brain.learn(
                run_id=rid, source=_SOURCE, category="pipeline",
                event_type=f"pipeline_{status}", detail=detail,
                outcome="pass" if status in ("started", "completed") else "error",
            )
        except Exception as e:
            print(f"[vinny-stack brain_bus] pipeline run error: {e}")
    return rid

def publish_inference_result(
    model: str,
    prompt_tokens: int,
    completion_tokens: int,
    latency_ms: float,
    outcome: str = "pass",
    run_id: str | None = None,
) -> bool:
    """Log token cost + latency from the infer module."""
    return publish_module_event(
        "infer", "inference_completed",
        detail=(
            f"model={model} prompt_tokens={prompt_tokens} "
            f"completion_tokens={completion_tokens} latency_ms={latency_ms:.0f}"
        ),
        outcome=outcome, run_id=run_id,
        metadata={
            "model": model,
            "total_tokens": prompt_tokens + completion_tokens,
            "latency_ms": latency_ms,
        },
    )

def publish_cache_event(
    key: str, hit: bool,
    size_bytes: int = 0, run_id: str | None = None,
) -> bool:
    """Log a cache hit/miss from the cache module."""
    return publish_module_event(
        "cache",
        "cache_hit" if hit else "cache_miss",
        detail=f"key={key} size_bytes={size_bytes}",
        outcome="pass", run_id=run_id,
        metadata={"key": key, "hit": hit, "size_bytes": size_bytes},
    )

def publish_classify_event(
    item: str, label: str, confidence: float,
    run_id: str | None = None,
) -> bool:
    """Log a classification result from the classify module."""
    return publish_module_event(
        "classify", "classification_result",
        detail=f"item={item} label={label} confidence={confidence:.3f}",
        outcome="pass", run_id=run_id,
        metadata={"item": item, "label": label, "confidence": confidence},
    )

def publish_evaluate_event(
    artifact: str, score: float,
    passed: bool, run_id: str | None = None,
) -> bool:
    """Log an evaluation result from the evaluate module."""
    brain = get_client()
    rid = run_id or f"vs_eval_{uuid.uuid4().hex[:8]}"
    if brain:
        try:
            brain.record_artifact(
                artifact_name=artifact,
                promotion_status="promoted" if passed else "rejected",
                trace_id=rid,
                notes=f"score={score:.3f}",
                runtime_pass=1 if passed else 0,
                runtime_fail=0 if passed else 1,
            )
        except Exception:
            pass
    return publish_module_event(
        "evaluate", "evaluation_completed",
        detail=f"artifact={artifact} score={score:.3f} passed={passed}",
        outcome="pass" if passed else "error", run_id=rid,
    )

def publish_audit_event(
    gate: str, result: str,
    detail: str = "", run_id: str | None = None,
) -> bool:
    """Log a gate audit result from the audit module (IDKWIDK 7-gate protocol)."""
    return publish_module_event(
        "audit", f"gate_{gate}_result",
        detail=f"gate={gate} result={result} | {detail}",
        outcome="pass" if result == "PASS" else "error",
        run_id=run_id,
    )

def publish_export_event(
    export_format: str, destination: str,
    record_count: int, outcome: str = "pass",
    run_id: str | None = None,
) -> bool:
    """Log an export event from the export module."""
    return publish_module_event(
        "export", "export_completed",
        detail=f"format={export_format} dest={destination} records={record_count}",
        outcome=outcome, run_id=run_id,
    )
