"""Text extraction with a Docling-first strategy and graceful fallback.

Backend order:
  1. **Docling** (intended primary). Best table/layout extraction, which is what
     makes German amount/VAT parsing reliable. This is also the engine wrapped by
     the ``docling_preprocessor_factory`` repo — to reuse that factory directly,
     add a public ``extract(path)`` method there and call it from
     ``_extract_with_factory`` below.
  2. **Light** fallback (pdfplumber/pypdf for PDFs, pytesseract for images) so the
     prototype runs without the heavy Docling/torch stack installed.
  3. If no backend can read a file, it is flagged (``OCR_REQUIRED`` /
     ``BACKEND_UNAVAILABLE``) and routed to manual review — never a crash.

Nothing here touches the network during extraction. (Docling may download models
on first use; see the README privacy note about warming up + ``HF_HUB_OFFLINE``.)
"""

from __future__ import annotations

import importlib.util
import logging
import shutil
from pathlib import Path

from .models import ExtractionResult, ExtractionStatus

# pypdf / pdfminer emit noisy warnings ("Ignoring wrong pointing object ...")
# on many real-world PDFs. They are harmless; keep the console clean.
logging.getLogger("pypdf").setLevel(logging.ERROR)
logging.getLogger("pdfminer").setLevel(logging.ERROR)

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".tif", ".tiff"}
EXTRACTION_BACKENDS = ("auto", "docling", "light")

_MIN_USEFUL_CHARS = 20


def _module_available(name: str) -> bool:
    return importlib.util.find_spec(name) is not None


def _tesseract_available() -> bool:
    return shutil.which("tesseract") is not None and _module_available("pytesseract")


# --- backends ------------------------------------------------------------

def _extract_with_factory(path: Path) -> ExtractionResult | None:
    """Reuse the docling_preprocessor_factory if it is installed.

    Returns ``None`` when the factory is not importable, so the caller falls
    through to the next backend. Expects a public ``extract(path)`` helper.
    """
    if not _module_available("docling_preprocessor_factory"):
        return None
    try:  # pragma: no cover - depends on optional external package
        from docling_preprocessor_factory import extract  # type: ignore

        records = extract(str(path))
        text = "\n".join(
            (r.get("text_markdown") or "") + "\n" + (r.get("ocr_image_text") or "")
            for r in records
        ).strip()
        ocr = any(r.get("ocr_image_text") for r in records)
        return ExtractionResult(
            text=text,
            unit_count=len(records),
            ocr_used=ocr,
            status=ExtractionStatus.OCR_USED if ocr else ExtractionStatus.OK,
            backend="docling_factory",
        )
    except Exception as exc:  # pragma: no cover
        return ExtractionResult(
            status=ExtractionStatus.ERROR, backend="docling_factory", error=str(exc)
        )


def _extract_with_docling(path: Path) -> ExtractionResult | None:
    if not _module_available("docling"):
        return None
    try:  # pragma: no cover - depends on optional heavy package
        from docling.document_converter import DocumentConverter

        converter = DocumentConverter()
        result = converter.convert(str(path))
        text = result.document.export_to_markdown()
        pages = getattr(result.document, "pages", None)
        unit_count = len(pages) if pages else 1
        is_image = path.suffix.lower() in IMAGE_EXTS
        return ExtractionResult(
            text=text or "",
            unit_count=unit_count,
            ocr_used=is_image,
            status=ExtractionStatus.OCR_USED if is_image else ExtractionStatus.OK,
            backend="docling",
        )
    except Exception as exc:  # pragma: no cover
        return ExtractionResult(
            status=ExtractionStatus.ERROR, backend="docling", error=str(exc)
        )


def _extract_pdf_light(path: Path) -> ExtractionResult:
    text = ""
    if _module_available("pdfplumber"):
        try:
            import pdfplumber

            with pdfplumber.open(str(path)) as pdf:
                pages = pdf.pages
                text = "\n".join((p.extract_text() or "") for p in pages)
                unit_count = len(pages)
            return _finish_pdf(text, unit_count, "pdfplumber")
        except Exception as exc:
            return ExtractionResult(
                status=ExtractionStatus.ERROR, backend="pdfplumber", error=str(exc)
            )
    if _module_available("pypdf"):
        try:
            from pypdf import PdfReader

            reader = PdfReader(str(path))
            if reader.is_encrypted:
                return ExtractionResult(
                    status=ExtractionStatus.ERROR,
                    backend="pypdf",
                    error="password-protected PDF",
                )
            text = "\n".join((page.extract_text() or "") for page in reader.pages)
            return _finish_pdf(text, len(reader.pages), "pypdf")
        except Exception as exc:
            return ExtractionResult(
                status=ExtractionStatus.ERROR, backend="pypdf", error=str(exc)
            )
    return ExtractionResult(status=ExtractionStatus.BACKEND_UNAVAILABLE, backend="none")


def _finish_pdf(text: str, unit_count: int, backend: str) -> ExtractionResult:
    if len(text.strip()) >= _MIN_USEFUL_CHARS:
        return ExtractionResult(
            text=text, unit_count=unit_count, status=ExtractionStatus.OK, backend=backend
        )
    # Embedded text too short -> scanned PDF, needs OCR (a later step).
    return ExtractionResult(
        text=text, unit_count=unit_count,
        status=ExtractionStatus.OCR_REQUIRED, backend=backend,
    )


def _extract_image_light(path: Path) -> ExtractionResult:
    if not _tesseract_available():
        return ExtractionResult(
            status=ExtractionStatus.OCR_REQUIRED, backend="none",
            error="Tesseract OCR not installed",
        )
    try:
        import pytesseract
        from PIL import Image

        text = pytesseract.image_to_string(Image.open(str(path)), lang="deu+eng")
        status = (
            ExtractionStatus.OCR_USED
            if len(text.strip()) >= _MIN_USEFUL_CHARS
            else ExtractionStatus.NO_TEXT
        )
        return ExtractionResult(
            text=text, unit_count=1, ocr_used=True, status=status, backend="pytesseract"
        )
    except Exception as exc:
        return ExtractionResult(
            status=ExtractionStatus.ERROR, backend="pytesseract", error=str(exc)
        )


# --- public API ----------------------------------------------------------

def extract_document(path: Path, backend: str = "auto") -> ExtractionResult:
    """Extract one document with a hybrid strategy.

    ``text`` = richest view (Docling markdown) for amount/metadata extraction.
    ``classification_text`` = a plain-text view for keyword classification:
    we prefer the light backend's plain text (it classifies best), and fall
    back to a flattened version of the rich text.

    ``backend`` controls the primary extraction view:
    ``auto``/``docling`` prefer Docling and fall back to light extraction;
    ``light`` skips Docling and uses only pdfplumber/pypdf/Tesseract.
    """
    from .metadata_extraction import normalize_for_classification

    path = Path(path)
    is_image = path.suffix.lower() in IMAGE_EXTS
    backend = backend.lower()
    if backend not in EXTRACTION_BACKENDS:
        raise ValueError(f"unsupported extraction backend: {backend}")

    if backend == "light":
        primary = _extract_image_light(path) if is_image else _extract_pdf_light(path)
        primary.classification_text = primary.text
        return primary

    # --- amount/metadata view: Docling preferred, else light ---
    primary: ExtractionResult | None = None
    for backend in (_extract_with_factory, _extract_with_docling):
        result = backend(path)
        if result is not None and result.status in (
            ExtractionStatus.OK,
            ExtractionStatus.OCR_USED,
        ):
            primary = result
            break
    if primary is None:
        primary = _extract_image_light(path) if is_image else _extract_pdf_light(path)

    # --- classification view ---
    if primary.backend in ("pdfplumber", "pypdf"):
        primary.classification_text = primary.text  # already plain
    elif not is_image:
        light = _extract_pdf_light(path)
        if light.text and len(light.text.strip()) >= _MIN_USEFUL_CHARS:
            primary.classification_text = light.text
    if not primary.classification_text:
        primary.classification_text = normalize_for_classification(primary.text)

    return primary


def active_backend() -> str:
    """Report which primary backend is available (for the console summary)."""
    if _module_available("docling_preprocessor_factory"):
        return "docling_factory"
    if _module_available("docling"):
        return "docling"
    if _module_available("pdfplumber") or _module_available("pypdf"):
        return "light (pdfplumber/pypdf)"
    return "none"
