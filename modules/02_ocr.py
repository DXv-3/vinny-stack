"""modules/02_ocr.py  —  vinny-stack stage 02: OCR

Extracts text from images and PDFs using local engines.

Backend priority:
  1. Apple Vision (macOS 13+ / via pyobjc or subprocess)  — best quality
  2. Tesseract OCR (pytesseract + Pillow)                  — cross-platform
  3. pdfminer.six (PDF text extraction, no OCR needed)     — for text PDFs
  4. Pass-through: if mime is text/*, raw_text already set by capture

Artifact inputs:
  raw_bytes   bytes  Raw file content
  mime        str    MIME type from capture stage
  raw_text    str    Pre-existing text (skip OCR if already set)

Artifact outputs:
  raw_text    str    Extracted text (appended to existing if present)
  ocr_engine  str    Engine used: 'apple_vision'|'tesseract'|'pdfminer'|'passthrough'
  ocr_pages   int    Number of pages processed (PDFs)

Config:
  VINNY_OCR_ENGINE  'auto'|'apple_vision'|'tesseract'|'pdfminer'  (default: auto)
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any, Dict, Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _brain_client import emit_stage  # noqa: E402

OCR_ENGINE = os.environ.get('VINNY_OCR_ENGINE', 'auto')


def _ocr_apple_vision(raw_bytes: bytes) -> Optional[str]:
    """Use macOS Vision framework via subprocess (no pyobjc required)."""
    try:
        import subprocess, tempfile, json as _json
        with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as tmp:
            tmp.write(raw_bytes)
            tmp_path = tmp.name
        # Swift one-liner that OCRs the image file and prints JSON
        swift_code = f"""
import Vision, Foundation
let url = URL(fileURLWithPath: \"{tmp_path}\")
let req = VNRecognizeTextRequest()
req.recognitionLevel = .accurate
let handler = VNImageRequestHandler(url: url)
try? handler.perform([req])
let obs = req.results as? [VNRecognizedTextObservation] ?? []
let text = obs.compactMap {{ $0.topCandidates(1).first?.string }}.joined(separator: \" \")
print(text)
"""
        result = subprocess.run(
            ['swift', '-'], input=swift_code.encode(), capture_output=True, timeout=30
        )
        Path(tmp_path).unlink(missing_ok=True)
        if result.returncode == 0:
            text = result.stdout.decode('utf-8', errors='replace').strip()
            return text if text else None
        return None
    except Exception:
        return None


def _ocr_tesseract(raw_bytes: bytes) -> Optional[str]:
    try:
        from PIL import Image  # type: ignore
        import pytesseract    # type: ignore
        import io
        img = Image.open(io.BytesIO(raw_bytes))
        return pytesseract.image_to_string(img)
    except Exception as e:
        print(f'    [ocr] tesseract failed: {e}')
        return None


def _extract_pdf(raw_bytes: bytes) -> tuple[Optional[str], int]:
    try:
        from pdfminer.high_level import extract_text  # type: ignore
        import io
        text = extract_text(io.BytesIO(raw_bytes))
        # Estimate pages (rough: ~3000 chars per page)
        pages = max(1, len(text) // 3000)
        return text, pages
    except Exception as e:
        print(f'    [ocr] pdfminer failed: {e}')
        return None, 0


def run(artifact: Dict[str, Any], run_id: str = '') -> Dict[str, Any]:
    outcome = 'pass'
    detail  = ''

    try:
        mime:      str   = artifact.get('mime', '')
        raw_bytes: bytes = artifact.get('raw_bytes', b'')
        raw_text:  str   = artifact.get('raw_text', '') or ''

        # Already have text from capture (plain text file)
        if raw_text and mime.startswith('text/'):
            artifact['ocr_engine'] = 'passthrough'
            artifact['ocr_pages']  = 1
            detail = f'passthrough — text already extracted by capture (mime={mime})'
            print(f'    {detail}')
            emit_stage(run_id=run_id, stage_name='ocr', outcome='pass', detail=detail)
            return artifact

        engine_used = 'none'
        extracted   = ''
        pages       = 1

        if mime == 'application/pdf':
            text, pages = _extract_pdf(raw_bytes)
            if text:
                extracted   = text
                engine_used = 'pdfminer'

        elif mime.startswith('image/'):
            pref = OCR_ENGINE if OCR_ENGINE != 'auto' else 'apple_vision'
            if pref == 'apple_vision' or OCR_ENGINE == 'auto':
                text = _ocr_apple_vision(raw_bytes)
                if text:
                    extracted   = text
                    engine_used = 'apple_vision'
            if not extracted and pref != 'apple_vision':
                text = _ocr_tesseract(raw_bytes)
                if text:
                    extracted   = text
                    engine_used = 'tesseract'
            if not extracted:
                # Tesseract fallback
                text = _ocr_tesseract(raw_bytes)
                if text:
                    extracted   = text
                    engine_used = 'tesseract'

        if extracted:
            artifact['raw_text']   = (raw_text + '\n\n' + extracted).strip() if raw_text else extracted
            artifact['ocr_engine'] = engine_used
            artifact['ocr_pages']  = pages
            detail = f'engine={engine_used} pages={pages} chars={len(extracted)}'
        else:
            artifact['ocr_engine'] = 'none'
            artifact['ocr_pages']  = 0
            detail = f'no text extracted from mime={mime}'

        print(f'    {detail}')

    except Exception as exc:
        outcome = 'fail'
        detail  = str(exc)[:200]
        artifact['ocr_error'] = detail
        print(f'    ERROR: {exc}')

    emit_stage(run_id=run_id, stage_name='ocr', outcome=outcome, detail=detail)
    return artifact
