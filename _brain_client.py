"""_brain_client.py  —  Shared bootstrap for brain bus + brain_sync integration.

Priority order:
  1. harmony-engine-protocol BrainBusPublisher  (preferred: async, fire-and-forget)
  2. brain_sync.get_brain()                     (fallback: direct SQLite write)
  3. None                                       (graceful no-op)

All vinny-stack modules import from here:
    from _brain_client import get_bus, get_client
"""
from __future__ import annotations
import os, sys
from pathlib import Path
from typing import Optional

_HERE = Path(__file__).resolve().parent

# ---------------------------------------------------------------------------
# 1. Harmony bus (preferred)
# ---------------------------------------------------------------------------

_bus: Optional[object] = None
_bus_resolved = False

def get_bus(source_repo: str = "vinny-stack"):
    """Return a BrainBusPublisher or None."""
    global _bus, _bus_resolved
    if _bus_resolved:
        return _bus
    _bus_resolved = True

    candidates = [
        os.environ.get("HARMONY_PATH", ""),
        str(_HERE.parent / "harmony-engine-protocol"),
        str(Path.home() / "harmony-engine-protocol"),
        str(Path.home() / "repos" / "harmony-engine-protocol"),
    ]
    for c in candidates:
        if c and (Path(c) / "brain_bus.py").exists():
            if c not in sys.path:
                sys.path.insert(0, c)
            try:
                from brain_bus import BrainBusPublisher  # type: ignore
                _bus = BrainBusPublisher(source_repo=source_repo)
                return _bus
            except Exception as e:
                print(f"[brain_client] harmony bus error from {c}: {e}")
    return None


# ---------------------------------------------------------------------------
# 2. Direct brain_sync fallback
# ---------------------------------------------------------------------------

_client = None
_client_resolved = False

def get_client():
    """Return brain_sync client or None."""
    global _client, _client_resolved
    if _client_resolved:
        return _client
    _client_resolved = True

    candidates = [
        os.environ.get("BRAIN_SYNC_PATH", ""),
        str(_HERE.parent / "the-brain"),
        str(Path.home() / "the-brain"),
        str(Path.home() / "repos" / "the-brain"),
    ]
    for c in candidates:
        if c and (Path(c) / "brain_sync.py").exists():
            if c not in sys.path:
                sys.path.insert(0, c)
            try:
                from brain_sync import get_brain  # type: ignore
                _client = get_brain()
                return _client
            except Exception as e:
                print(f"[brain_client] brain_sync error from {c}: {e}")
    return None


# ---------------------------------------------------------------------------
# Convenience: emit a pipeline stage event (bus-first, sync fallback)
# ---------------------------------------------------------------------------

def emit_stage(
    run_id:     str,
    stage_name: str,
    outcome:    str,      # "pass" | "fail"
    detail:     str = "",
    model:      str = "",
) -> bool:
    """
    Emit a pipeline stage event to the brain bus (or brain_sync fallback).
    Never raises. Returns True if emitted.
    """
    bus = get_bus()
    if bus is not None:
        try:
            return bus.publish_learn(
                run_id     = run_id,
                source     = "vinny-stack",
                category   = "pipeline_stage",
                event_type = "GATE_PASSED" if outcome == "pass" else "GATE_FAILED",
                detail     = f"stage={stage_name} model={model} {detail[:180]}".strip(),
                outcome    = outcome,
            )
        except Exception:
            pass
    return False
