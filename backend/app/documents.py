from __future__ import annotations

import io
import re
from typing import Any

from pypdf import PdfReader
from pypdf.errors import PdfReadError

from .scanner import redact_secret_values

MAX_PDF_BYTES = 5 * 1024 * 1024
MAX_PDF_PAGES = 25
MAX_DOCUMENT_CHARS = 50_000
MAX_NOTICE_DOCUMENTS = 5

EMAIL_RE = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.I)
PHONE_RE = re.compile(r"(?<!\w)(?:\+?91[\s.-]?)?[6-9]\d{4}[\s.-]?\d{5}(?!\w)")


class DocumentError(ValueError):
    pass


def _redact_excerpt(value: str, *, resume: bool) -> str:
    text = redact_secret_values(value) if resume else value
    if resume:
        text = EMAIL_RE.sub("[EMAIL REDACTED]", text)
        text = PHONE_RE.sub("[PHONE REDACTED]", text)
    return text[:500]


def _make_document(
    name: str,
    source_type: str,
    pages: list[str],
    prefix: str,
    *,
    resume: bool = False,
) -> dict[str, Any]:
    total_chars = sum(len(page) for page in pages)
    if total_chars > MAX_DOCUMENT_CHARS:
        raise DocumentError("This document contains over 50,000 extracted characters. Shorten it and try again.")
    evidence: list[dict[str, Any]] = []
    for page_index, page in enumerate(pages, 1):
        lines = page.splitlines()
        for line_index, line in enumerate(lines, 1):
            if not line.strip():
                continue
            excerpt = _redact_excerpt(line.strip(), resume=resume)
            evidence.append({
                "id": f"{prefix}{len(evidence) + 1:04d}",
                "path": name,
                "source_name": name,
                "source_type": source_type,
                "source_id": prefix.rstrip("-"),
                "page_number": page_index if len(pages) > 1 or source_type.endswith("_pdf") else None,
                "page_count": len(pages) if source_type.endswith("_pdf") else None,
                "line_start": line_index,
                "line_end": line_index,
                "line_count": len(lines),
                "excerpt": excerpt,
                "kind": f"{source_type}_line",
                "extractor": "pdf_page_text" if source_type.endswith("_pdf") else "pasted_text",
            })
    if not evidence:
        raise DocumentError("No readable text was found in this document.")
    return {"name": name, "source_type": source_type, "evidence": evidence}


def text_document(name: str, text: str, source_type: str, prefix: str, *, resume: bool = False) -> dict[str, Any]:
    if not text or not text.strip():
        raise DocumentError("Paste some document text before submitting.")
    if len(text) > MAX_DOCUMENT_CHARS:
        raise DocumentError("Pasted text is limited to 50,000 characters per document.")
    safe_name = name.strip()[:120] or ("Resume text" if resume else "Notice text")
    return _make_document(safe_name, source_type, [text], prefix, resume=resume)


def pdf_document(data: bytes, filename: str, source_type: str, prefix: str, *, resume: bool = False) -> dict[str, Any]:
    if len(data) > MAX_PDF_BYTES:
        raise DocumentError("Each PDF must be 5 MB or smaller.")
    if not data.startswith(b"%PDF-"):
        raise DocumentError("Upload a valid PDF file.")
    safe_name = "Resume PDF" if resume else (filename.replace("\\", "/").rsplit("/", 1)[-1][:120] or "document.pdf")
    try:
        reader = PdfReader(io.BytesIO(data), strict=False)
        if reader.is_encrypted:
            raise DocumentError("Password-protected PDFs are not supported. Upload an unlocked copy.")
        if len(reader.pages) > MAX_PDF_PAGES:
            raise DocumentError("Each PDF is limited to 25 pages.")
        pages = [(page.extract_text() or "") for page in reader.pages]
    except DocumentError:
        raise
    except (PdfReadError, OSError, ValueError) as exc:
        raise DocumentError(f"Could not read this PDF: {exc}") from None
    if not any(page.strip() for page in pages):
        raise DocumentError("This PDF has no selectable text. Paste its text; image-only PDFs are not supported.")
    return _make_document(safe_name, source_type, pages, prefix, resume=resume)


def trim_document_evidence(document: dict[str, Any], limit: int = 150) -> list[dict[str, Any]]:
    items = document["evidence"]
    if len(items) <= limit:
        return items
    priority = re.compile(r"(?i)(deadline|due|last date|eligib|qualif|criteria|apply|application|submit|upload|fee|interview|date|time|required|must|should|claim|built|developed|designed|implemented|led|reduced|increased|improved|delivered)")
    selected = {item["id"]: item for item in items[:min(8, limit)]}
    for item in items:
        if priority.search(item["excerpt"]):
            selected[item["id"]] = item
            if len(selected) >= limit:
                break
    if len(selected) < limit:
        stride = max(1, len(items) // (limit - len(selected)))
        for item in items[::stride]:
            selected[item["id"]] = item
            if len(selected) >= limit:
                break
    return sorted(selected.values(), key=lambda item: item["id"])
