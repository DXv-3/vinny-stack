#!/usr/bin/env python3
"""pipeline.py  —  vinny-stack 25-stage local-first AI pipeline orchestrator.

USAGE
-----
    python pipeline.py --input path/to/file_or_url [--stages all] [--run-id custom-id]
    python pipeline.py --input note.md --stages capture,chunk,embed,cache,store,index
    python pipeline.py --input https://github.com/DXv-3/the-brain --stages capture,ocr,chunk,embed

Each stage emits GATE_PASSED or GATE_FAILED to the brain bus so every run
is visible in the-brain dashboard and conductors pre-route query history.

Stages that are skipped (not in --stages) emit nothing and return their
input unchanged, so partial pipelines are first-class.
"""
from __future__ import annotations

import argparse
import importlib
import sys
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

# Brain bus bootstrap — bus-first, sync fallback, graceful no-op
from _brain_client import emit_stage, get_bus

# ---------------------------------------------------------------------------
# Stage registry (order matters)
# ---------------------------------------------------------------------------

STAGES: List[str] = [
    "capture",    # 01
    "ocr",        # 02
    "chunk",      # 03
    "embed",      # 04
    "cache",      # 05
    "search",     # 06
    "route",      # 07
    "infer",      # 08
    "validate",   # 09
    "rerank",     # 10
    "extract",    # 11
    "normalize",  # 12
    "dedup",      # 13
    "classify",   # 14
    "tag",        # 15
    "relate",     # 16
    "summarize",  # 17
    "store",      # 18
    "index",      # 19
    "export",     # 20
    "notify",     # 21
    "review",     # 22
    "audit",      # 23
    "mutate",     # 24
    "dashboard",  # 25
]

# ---------------------------------------------------------------------------
# Stage loader
# ---------------------------------------------------------------------------

def _load_stage(name: str):
    """
    Try to import modules/<nn>_<name>.py.  Returns None if not yet built.
    This lets the orchestrator run gracefully even if only some modules exist.
    """
    modules_dir = Path(__file__).parent / "modules"
    # Find matching file e.g. modules/01_capture.py
    matches = sorted(modules_dir.glob(f"*_{name}.py")) if modules_dir.exists() else []
    if not matches:
        return None
    mod_path = matches[0]
    spec_name = f"vinny_modules.{name}"
    if spec_name not in sys.modules:
        import importlib.util
        spec = importlib.util.spec_from_file_location(spec_name, mod_path)
        if spec and spec.loader:
            mod = importlib.util.module_from_spec(spec)
            sys.modules[spec_name] = mod
            spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return sys.modules.get(spec_name)


# ---------------------------------------------------------------------------
# Stub runner (used when module file does not exist yet)
# ---------------------------------------------------------------------------

def _stub_run(stage_name: str, artifact: Any, run_id: str) -> Any:
    """
    Placeholder that passes the artifact through unchanged and emits a
    GATE_PASSED event so the run still appears in the brain dashboard.
    """
    print(f"  [stub] {stage_name}: module not yet built — pass-through")
    emit_stage(run_id=run_id, stage_name=stage_name, outcome="pass",
               detail="stub pass-through (module not yet implemented)")
    return artifact


# ---------------------------------------------------------------------------
# Pipeline runner
# ---------------------------------------------------------------------------

def run_pipeline(
    input_path: str,
    stages:     List[str],
    run_id:     Optional[str] = None,
    extra_ctx:  Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Execute the requested stages in order.  Each stage receives and returns
    an `artifact` dict that accumulates all pipeline state.

    Returns a summary dict with:
      run_id, stages_run, stages_passed, stages_failed, artifact
    """
    _run_id = run_id or f"vinny_{uuid.uuid4().hex[:12]}"
    extra_ctx = extra_ctx or {}

    # Normalise stage list
    if stages == ["all"]:
        active_stages = STAGES[:]
    else:
        active_stages = [s.strip().lower() for s in stages if s.strip().lower() in STAGES]
        unknown = [s for s in stages if s.strip().lower() not in STAGES]
        if unknown:
            print(f"[pipeline] Unknown stages ignored: {unknown}")

    print(f"\n[vinny-stack] run_id={_run_id}")
    print(f"[vinny-stack] input={input_path}")
    print(f"[vinny-stack] stages={active_stages}\n")

    # Announce run start to brain bus
    bus = get_bus()
    if bus:
        try:
            bus.publish_ping(subsystem_name="vinny-stack", status="running")
        except Exception:
            pass

    artifact: Dict[str, Any] = {
        "input_path": input_path,
        "run_id":     _run_id,
        **extra_ctx,
    }

    stages_passed: List[str] = []
    stages_failed: List[str] = []

    for stage_name in STAGES:
        if stage_name not in active_stages:
            continue

        print(f"  [{stage_name}] ▶", end=" ", flush=True)
        mod = _load_stage(stage_name)

        if mod is None or not hasattr(mod, "run"):
            # Module not built yet — stub pass-through
            artifact = _stub_run(stage_name, artifact, _run_id)
            stages_passed.append(stage_name)
            continue

        try:
            artifact = mod.run(artifact, run_id=_run_id)
            # Modules are expected to call emit_stage themselves, but we
            # emit a fallback PASS here if they don’t (double-emit is harmless).
            emit_stage(
                run_id=_run_id, stage_name=stage_name, outcome="pass",
                detail=f"input_path={input_path[:80]}",
            )
            stages_passed.append(stage_name)
            print(f"✓")
        except Exception as exc:
            emit_stage(
                run_id=_run_id, stage_name=stage_name, outcome="fail",
                detail=str(exc)[:200],
            )
            stages_failed.append(stage_name)
            print(f"✗  {exc}")
            # Non-fatal: continue pipeline with unchanged artifact

    # Announce completion
    if bus:
        try:
            status = "pass" if not stages_failed else "partial"
            bus.publish_ping(subsystem_name="vinny-stack", status=status)
        except Exception:
            pass

    summary = {
        "run_id":        _run_id,
        "stages_run":    active_stages,
        "stages_passed": stages_passed,
        "stages_failed": stages_failed,
        "artifact":      artifact,
    }
    print(f"\n[vinny-stack] done. passed={len(stages_passed)} failed={len(stages_failed)}")
    return summary


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="vinny-stack: 25-stage local-first AI pipeline"
    )
    parser.add_argument(
        "--input", required=True,
        help="Input file path or URL"
    )
    parser.add_argument(
        "--stages", default="all",
        help="Comma-separated stage names or 'all' (default: all)"
    )
    parser.add_argument(
        "--run-id", default=None,
        help="Custom run ID (auto-generated if omitted)"
    )
    args = parser.parse_args()

    stage_list = [s.strip() for s in args.stages.split(",")]
    result = run_pipeline(
        input_path = args.input,
        stages     = stage_list,
        run_id     = args.run_id,
    )
    import json
    # Print summary without the full artifact blob
    print(json.dumps({
        k: v for k, v in result.items() if k != "artifact"
    }, indent=2))
