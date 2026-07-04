# vinny-stack module map

Each module lives at `modules/<nn>_<name>.py` and exposes:

```python
def run(artifact: dict, run_id: str = '') -> dict:
    ...  # mutate artifact, call emit_stage(), return artifact
```

The orchestrator (`pipeline.py`) dynamically loads modules by name.  
Stages with no module file run as a **stub pass-through** (pipeline never hard-fails).

---

## Stage Map

| # | Name | Status | Key Inputs | Key Outputs |
|---|------|--------|------------|-------------|
| 01 | capture | ✅ built | `input_path` | `raw_bytes`, `raw_text`, `mime`, `source_type` |
| 02 | ocr | ✅ built | `raw_bytes`, `mime` | `raw_text` (appended), `ocr_engine` |
| 03 | chunk | ✅ built | `raw_text` | `chunks[]` (text, char_start, heading, token_est) |
| 04 | embed | ✅ built | `chunks[]` | `chunks[].vector`, `embed_model`, `embed_dim` |
| 05 | cache | 🟡 stub | `chunks[]` | `cache_hits[]`, `cache_misses[]` |
| 06 | search | 🟡 stub | `chunks[]` | `search_results[]` |
| 07 | route | 🟡 stub | artifact | `route_target`, `route_reason` |
| 08 | infer | 🟡 stub | artifact | `inference_result`, `model_used` |
| 09 | validate | 🟡 stub | `inference_result` | `validation_passed`, `issues[]` |
| 10 | rerank | 🟡 stub | `search_results[]` | reranked `search_results[]` |
| 11 | extract | 🟡 stub | `raw_text` | `entities[]`, `relations[]` |
| 12 | normalize | 🟡 stub | `entities[]` | normalized `entities[]` |
| 13 | dedup | 🟡 stub | `chunks[]` | deduplicated `chunks[]` |
| 14 | classify | 🟡 stub | `raw_text` | `category`, `confidence` |
| 15 | tag | 🟡 stub | artifact | `tags[]` |
| 16 | relate | 🟡 stub | `entities[]` | KG edges written to brain.db |
| 17 | summarize | 🟡 stub | `raw_text` | `summary`, `summary_model` |
| 18 | store | ✅ built | all above | `brain_record_id`, `store_status` |
| 19 | index | 🟡 stub | `brain_record_id` | full-text + vector index updated |
| 20 | export | 🟡 stub | artifact | `export_path`, `export_format` |
| 21 | notify | 🟡 stub | artifact | push/webhook notification sent |
| 22 | review | 🟡 stub | artifact | `review_flags[]` |
| 23 | audit | 🟡 stub | all | IDKWIDK gate results written to brain |
| 24 | mutate | 🟡 stub | `audit` results | `skill.md` updated if gate passed |
| 25 | dashboard | 🟡 stub | run summary | brain-dashboard panel refreshed |

---

## Quick presets (via `run_quick.sh`)

```
ingest  →  capture → chunk → embed → store
ocr     →  capture → ocr → chunk → embed → store
url     →  capture → chunk → embed → summarize → store
full    →  all 25 stages
```

## Extension contract

```python
# modules/05_cache.py skeleton
from __future__ import annotations
from typing import Any, Dict
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _brain_client import emit_stage

def run(artifact: Dict[str, Any], run_id: str = '') -> Dict[str, Any]:
    # 1. Read from artifact
    # 2. Do your thing
    # 3. Write results back to artifact
    # 4. emit_stage() to report to brain dashboard
    emit_stage(run_id=run_id, stage_name='cache', outcome='pass', detail='...')
    return artifact
```

That’s it.  Drop the file in `modules/` and `pipeline.py` auto-discovers it.
