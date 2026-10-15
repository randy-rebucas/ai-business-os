"""OCR adapter for scanned PDF pages (pipeline step 4, ADR-014).

Uses Tesseract via pytesseract + pypdfium2 (`pip install -e ".[ocr]"` and the `tesseract` binary on PATH). When
either is missing, `available()` is False and the pipeline records an explicit `ocr_unavailable` warning (or fails
the document with `no_text_ocr_unavailable` if nothing else is readable) — it never pretends a scan was read.
"""

import shutil
from functools import lru_cache


@lru_cache
def available() -> bool:
    if shutil.which("tesseract") is None:
        return False
    try:
        import pypdfium2  # noqa: F401, PLC0415
        import pytesseract  # noqa: F401, PLC0415
    except ImportError:
        return False
    return True


def pdf_page_text(data: bytes, page_index: int) -> str:  # pragma: no cover - needs the Tesseract binary
    import pypdfium2  # noqa: PLC0415
    import pytesseract  # noqa: PLC0415

    pdf = pypdfium2.PdfDocument(data)
    try:
        image = pdf[page_index].render(scale=300 / 72).to_pil()
        return pytesseract.image_to_string(image)
    finally:
        pdf.close()
