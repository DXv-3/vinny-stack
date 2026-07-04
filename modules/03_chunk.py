"""modules/03_chunk.py  —  vinny-stack stage 03: CHUNK

Splits raw_text into semantic chunks suitable for embedding.

Strategy:
  1. Markdown-aware: splits on heading boundaries first (## / ###)
  2. Paragraph-aware: splits on blank lines within sections
  3. Sentence-aware: splits long paragraphs at sentence boundaries
  4. Hard cap: any chunk over chunk_size chars is split at the cap
     with overlap carry-forward

Artifact inputs:
  raw_text    str   Text to chunk (from capture or ocr stage)

Artifact outputs:
  chunks      list[dict]  Each chunk:
    index       int    0-based chunk number
    text        str    Chunk content
    char_start  int    Character offset in raw_text
    char_end    int    Character offset in raw_text
    heading     str    Nearest markdown heading (if any)
    token_est   int    Estimated token count (chars / 4)

Config (via artifact or env):
  VINNY_CHUNK_SIZE     int  Target chars per chunk  (default 1200)
  VINNY_CHUNK_OVERLAP  int  Overlap chars between chunks (default 150)
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path
from typing import Any, Dict, List

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _brain_client import emit_stage  # noqa: E402

DEFAULT_CHUNK_SIZE    = int(os.environ.get('VINNY_CHUNK_SIZE',    '1200'))
DEFAULT_CHUNK_OVERLAP = int(os.environ.get('VINNY_CHUNK_OVERLAP', '150'))

# Regex: markdown headings h1-h3
_HEADING_RE = re.compile(r'^(#{1,3})\s+(.+)$', re.MULTILINE)
# Sentence-end detection (basic, language-agnostic)
_SENT_END_RE = re.compile(r'(?<=[.!?])\s+')


def _split_sentences(text: str) -> List[str]:
    """Split text into sentences at punctuation + whitespace boundaries."""
    parts = _SENT_END_RE.split(text)
    return [p.strip() for p in parts if p.strip()]


def _paragraphs(text: str) -> List[str]:
    """Split on blank lines."""
    return [p.strip() for p in re.split(r'\n{2,}', text) if p.strip()]


def _chunk_text(
    text: str,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    overlap: int    = DEFAULT_CHUNK_OVERLAP,
) -> List[Dict[str, Any]]:
    """
    Core chunking logic.  Returns list of chunk dicts.
    """
    chunks: List[Dict[str, Any]] = []
    current_heading = ''
    pos = 0

    # Step 1: identify heading-bounded sections
    sections: List[Dict[str, Any]] = []
    heading_positions = [(m.start(), m.group(2), m.end()) for m in _HEADING_RE.finditer(text)]

    if not heading_positions:
        # No headings — treat entire text as one section
        sections = [{'heading': '', 'text': text, 'start': 0}]
    else:
        # Build sections between headings
        for i, (hstart, htext, hend) in enumerate(heading_positions):
            next_hstart = heading_positions[i + 1][0] if i + 1 < len(heading_positions) else len(text)
            section_text = text[hend:next_hstart].strip()
            sections.append({'heading': htext, 'text': section_text, 'start': hend})
        # Text before first heading
        if heading_positions[0][0] > 0:
            preamble = text[:heading_positions[0][0]].strip()
            if preamble:
                sections.insert(0, {'heading': '', 'text': preamble, 'start': 0})

    # Step 2: chunk each section
    char_pos = 0
    carry: str = ''  # overlap carry from previous chunk

    for section in sections:
        heading   = section['heading']
        sec_text  = (carry + ' ' + section['text']).strip() if carry else section['text']
        carry     = ''
        paragraphs = _paragraphs(sec_text)

        buf      = ''
        buf_start = char_pos

        for para in paragraphs:
            if len(buf) + len(para) + 1 <= chunk_size:
                buf = (buf + '\n\n' + para).lstrip() if buf else para
            else:
                # Flush buf as a chunk
                if buf:
                    chunks.append({
                        'index':      len(chunks),
                        'text':       buf,
                        'char_start': buf_start,
                        'char_end':   buf_start + len(buf),
                        'heading':    heading,
                        'token_est':  len(buf) // 4,
                    })
                    carry  = buf[-overlap:] if overlap else ''
                    buf_start = buf_start + len(buf) - overlap
                    buf = carry + '\n\n' + para if carry else para

                # Para itself is too long — split at sentences
                if len(para) > chunk_size:
                    sentences = _split_sentences(para)
                    sbuf = ''
                    for sent in sentences:
                        if len(sbuf) + len(sent) + 1 <= chunk_size:
                            sbuf = (sbuf + ' ' + sent).lstrip() if sbuf else sent
                        else:
                            if sbuf:
                                chunks.append({
                                    'index':      len(chunks),
                                    'text':       sbuf,
                                    'char_start': buf_start,
                                    'char_end':   buf_start + len(sbuf),
                                    'heading':    heading,
                                    'token_est':  len(sbuf) // 4,
                                })
                                carry    = sbuf[-overlap:] if overlap else ''
                                buf_start = buf_start + len(sbuf) - overlap
                                sbuf     = (carry + ' ' + sent).lstrip() if carry else sent
                    if sbuf:
                        buf       = sbuf
                        buf_start = buf_start
                else:
                    buf = para

        # Flush remaining buffer for this section
        if buf:
            chunks.append({
                'index':      len(chunks),
                'text':       buf,
                'char_start': buf_start,
                'char_end':   buf_start + len(buf),
                'heading':    heading,
                'token_est':  len(buf) // 4,
            })
            carry = buf[-overlap:] if overlap else ''

        char_pos += len(section['text'])

    return chunks


def run(artifact: Dict[str, Any], run_id: str = '') -> Dict[str, Any]:
    outcome = 'pass'
    detail  = ''

    try:
        raw_text: str = artifact.get('raw_text', '') or ''

        if not raw_text:
            # If no text yet (e.g. image not yet OCR'd), skip gracefully
            artifact['chunks'] = []
            detail = 'no raw_text — skipped (run ocr stage first for images)'
            print(f'    skipped: {detail}')
            emit_stage(run_id=run_id, stage_name='chunk', outcome='pass', detail=detail)
            return artifact

        chunk_size = int(artifact.get('chunk_size', DEFAULT_CHUNK_SIZE))
        overlap    = int(artifact.get('chunk_overlap', DEFAULT_CHUNK_OVERLAP))

        chunks = _chunk_text(raw_text, chunk_size=chunk_size, overlap=overlap)
        artifact['chunks'] = chunks

        detail = f'n_chunks={len(chunks)} chunk_size={chunk_size} overlap={overlap}'
        print(f'    {detail}')

    except Exception as exc:
        outcome = 'fail'
        detail  = str(exc)[:200]
        artifact['chunk_error'] = detail
        artifact.setdefault('chunks', [])
        print(f'    ERROR: {exc}')

    emit_stage(run_id=run_id, stage_name='chunk', outcome=outcome, detail=detail)
    return artifact
