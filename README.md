# vinny-stack

> **Local-first AI pipeline. 25 novel modules. Zero cloud dependency.**
> Every stage emits telemetry to `the-brain` via `harmony-engine-protocol`.
> The conductor routes. The brain remembers. The system improves.

---

## Architecture

```
╔══════════════════════════════════════════════════════════════════════════╗
║                         VINNY-STACK PIPELINE                           ║
║  Input → [25 stages] → Output   (all stages emit to brain bus)         ║
╠══════════════════════════════════════════════════════════════════════════╣
║  CAPTURE  →  OCR  →  CHUNK  →  EMBED  →  CACHE                        ║
║     ↓                                         ↓                        ║
║  SEARCH  ←──────────────────────────────── (vector)                    ║
║     ↓                                                                   ║
║  ROUTE  →  INFER  →  VALIDATE  →  RERANK  →  EXTRACT                  ║
║                                                    ↓                   ║
║  NORMALIZE  →  DEDUP  →  CLASSIFY  →  TAG  →  RELATE                  ║
║                                                    ↓                   ║
║  SUMMARIZE  →  STORE  →  INDEX  →  EXPORT  →  NOTIFY                  ║
║                                                    ↓                   ║
║  REVIEW  →  AUDIT  →  MUTATE  →  DASHBOARD                            ║
╚══════════════════════════════════════════════════════════════════════════╝
                              ↕ harmony bus
                         brain.db (the-brain)
                              ↕
              conductor-protocol-v2  ←→  zai-wrap
```

---

## The 25 Modules

| # | Module | Role | Key I/O |
|---|--------|------|---------|
| 01 | **capture** | Ingest raw input: files, clipboard, screenshots, URLs, mic | `raw_input → artifact` |
| 02 | **ocr** | Extract text from images, PDFs, handwriting (local Tesseract/Apple Vision) | `image/pdf → text` |
| 03 | **chunk** | Split text into semantic chunks for embedding; respects sentence/paragraph boundaries | `text → chunks[]` |
| 04 | **embed** | Generate local vector embeddings (llama.cpp, GGUF embedding models) | `chunks[] → vectors[]` |
| 05 | **cache** | Deduplicate and store embeddings; skip re-embedding identical content | `vectors[] → cache_hit/miss` |
| 06 | **search** | Semantic vector search against brain.db FTS5 + vector store | `query → ranked_results[]` |
| 07 | **route** | Query conductor pre-route brain check; select model + gate config | `task_config → routed_config` |
| 08 | **infer** | Call LLM via zai-wrap model gateway (5 backends, fallback chain) | `prompt + model → response` |
| 09 | **validate** | Schema + semantic validation of LLM response; retry on failure | `response → validated/retry` |
| 10 | **rerank** | Cross-encoder reranking of candidate outputs by relevance score | `candidates[] → ranked[]` |
| 11 | **extract** | Structured extraction: entities, dates, URLs, code blocks, JSON | `text → structured_data` |
| 12 | **normalize** | Canonicalize dates, names, units, currencies, encodings | `raw_data → clean_data` |
| 13 | **dedup** | Content-hash deduplication across pipeline run outputs | `items[] → unique_items[]` |
| 14 | **classify** | Multi-label classification: document type, intent, sensitivity | `content → labels[]` |
| 15 | **tag** | Auto-tag with taxonomy derived from brain.db knowledge graph | `content → tags[]` |
| 16 | **relate** | Build KG edges: `CONTENT --[RELATES_TO]--> CONCEPT` in brain.db | `tagged_content → KG edges` |
| 17 | **summarize** | Hierarchical summarization: sentence → paragraph → document level | `chunks[] → summary` |
| 18 | **store** | Persist artifact + metadata to brain.db with provenance chain | `artifact → brain record` |
| 19 | **index** | Update FTS5 full-text index and vector index in brain.db | `brain record → indexed` |
| 20 | **export** | Export to markdown, JSON, CSV, PDF, clipboard, or second brain app | `brain record → file/clipboard` |
| 21 | **notify** | macOS notification, iOS push (via Shortcut webhook), or log line | `event → notification` |
| 22 | **review** | Human-in-the-loop gate: present output for approval before storing | `artifact → approved/rejected` |
| 23 | **audit** | 7-gate IDKWIDK audit log via self-improving-system-builder bridge | `run → audit_record` |
| 24 | **mutate** | Write updated skill.md back to self-improving-system-builder | `audit_record → skill_update` |
| 25 | **dashboard** | Emit pipeline run summary to the-brain live dashboard | `run_summary → dashboard event` |

---

## Quickstart

```bash
# 1. Clone alongside sibling repos
git clone https://github.com/DXv-3/vinny-stack ~/vinny-stack

# 2. Set env vars (or export in your shell profile)
export BRAIN_DB_PATH=~/.brain/brain.db
export BRAIN_BUS_SPOOL=~/.brain_bus_spool/
export BRAIN_SYNC_PATH=~/the-brain
export VINNY_LLM_BASE=http://localhost:1234/v1   # LM Studio / Ollama
export VINNY_LLM_MODEL=llama-3.2-3b

# 3. Run a full pipeline pass
python pipeline.py --input "path/to/file_or_url" --stages all

# 4. Run specific stages only
python pipeline.py --input "note.md" --stages capture,chunk,embed,cache,store,index

# 5. Query the pipeline's output in brain
curl -H "Authorization: Bearer $BRAIN_TOKEN" \
     "http://localhost:8765/search?q=vinny-stack+pipeline"
```

---

## Environment Variables

| Variable | Default | Purpose |
|----------|---------|----------|
| `BRAIN_DB_PATH` | `~/.brain/brain.db` | SQLite brain database |
| `BRAIN_BUS_SPOOL` | `~/.brain_bus_spool/` | Harmony bus spool directory |
| `BRAIN_SYNC_PATH` | `~/the-brain` | Path to brain_sync.py (fallback if bus unavailable) |
| `BRAIN_TOKEN` | — | MCP server auth token for remote brain queries |
| `VINNY_LLM_BASE` | `http://localhost:1234/v1` | Local LLM server base URL |
| `VINNY_LLM_MODEL` | `llama-3.2-3b` | Default local model name |
| `VINNY_OCR_ENGINE` | `tesseract` | OCR backend: `tesseract` or `apple_vision` |
| `VINNY_EMBED_MODEL` | `nomic-embed-text` | Local embedding model |
| `VINNY_EXPORT_FORMAT` | `markdown` | Default export format |
| `VINNY_REVIEW_MODE` | `auto` | `auto` skips human gate; `manual` prompts |

---

## Ecosystem Integration

```
vinny-stack                   connects to
─────────────────────────────────────────────────────
stage 07 route              → conductor-protocol-v2  (pre-route brain query)
stage 08 infer              → zai-wrap               (model gateway, 5 backends)
all stages                  → harmony-engine-protocol (brain bus, telemetry)
stage 18/19 store/index     → the-brain              (brain.db + FTS5 + KG)
stage 23 audit              → self-improving-system-builder (IDKWIDK gates)
stage 24 mutate             → self-improving-system-builder (skill.md updates)
stage 25 dashboard          → the-brain dashboard    (live run feed)
stages 13 dedup / 18 store  → MATRIX / PersonalStorageForge (file provenance)
```

Each stage that calls `infer` routes through `conductor-protocol-v2`, which:
1. Queries brain.db for historical failure data on this gate + model combo
2. Adjusts the model if needed (e.g. switch from grok-3 to claude for regex tasks)
3. Calls zai-wrap with the selected model
4. Emits the result back to brain.db via harmony bus
5. self-improving-system-builder learns from the pattern and updates skill.md

This makes the pipeline **self-improving**: every run makes the next run smarter.

---

## File Structure

```
vinny-stack/
├── pipeline.py              # 25-stage orchestrator (entry point)
├── _brain_client.py         # Brain bus bootstrap (harmony-first, sync fallback)
├── brain_bus_publisher.py   # BrainBusPublisher wrapper for vinny-stack
├── README.md                # This file
└── modules/                 # Individual stage implementations (TODO: build out)
    ├── 01_capture.py
    ├── 02_ocr.py
    ├── 03_chunk.py
    ├── 04_embed.py
    ├── 05_cache.py
    ├── 06_search.py
    ├── 07_route.py
    ├── 08_infer.py
    ├── 09_validate.py
    ├── 10_rerank.py
    ├── 11_extract.py
    ├── 12_normalize.py
    ├── 13_dedup.py
    ├── 14_classify.py
    ├── 15_tag.py
    ├── 16_relate.py
    ├── 17_summarize.py
    ├── 18_store.py
    ├── 19_index.py
    ├── 20_export.py
    ├── 21_notify.py
    ├── 22_review.py
    ├── 23_audit.py
    ├── 24_mutate.py
    └── 25_dashboard.py
```

---

*Part of the DXv-3 ecosystem. See [ECOSYSTEM.md in the-brain](https://github.com/DXv-3/the-brain/blob/main/ECOSYSTEM.md) for the full architecture.*
