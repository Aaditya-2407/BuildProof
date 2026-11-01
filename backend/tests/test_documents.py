from __future__ import annotations

import io

import pytest
from pypdf import PdfWriter

from app import document_analyzers
from app.analyzer import ModelError
from app.documents import DocumentError, pdf_document, text_document
from app.scanner import build_fact_sheet


def make_text_pdf(text: str) -> bytes:
    stream = f"BT /F1 12 Tf 20 100 Td ({text}) Tj ET".encode("ascii")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 300 144] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream",
    ]
    output = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for index, obj in enumerate(objects, 1):
        offsets.append(len(output))
        output.extend(f"{index} 0 obj\n".encode() + obj + b"\nendobj\n")
    xref = len(output)
    output.extend(f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode())
    for offset in offsets[1:]:
        output.extend(f"{offset:010d} 00000 n \n".encode())
    output.extend(f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF".encode())
    return bytes(output)


def test_pdf_extraction_keeps_page_and_line_citations():
    document = pdf_document(make_text_pdf("Deadline: 2026-11-10"), "notice.pdf", "notice_pdf", "N1-")
    evidence = document["evidence"][0]
    assert evidence["page_number"] == 1
    assert evidence["line_start"] == evidence["line_end"] == 1
    assert "2026-11-10" in evidence["excerpt"]


def test_pdf_limits_and_image_only_pdf_errors():
    with pytest.raises(DocumentError, match="5 MB"):
        pdf_document(b"%PDF-" + b"0" * (5 * 1024 * 1024), "large.pdf", "notice_pdf", "N1-")

    writer = PdfWriter()
    for _ in range(26):
        writer.add_blank_page(width=300, height=144)
    too_many_pages = io.BytesIO()
    writer.write(too_many_pages)
    with pytest.raises(DocumentError, match="25 pages"):
        pdf_document(too_many_pages.getvalue(), "long.pdf", "notice_pdf", "N1-")

    blank = PdfWriter()
    blank.add_blank_page(width=300, height=144)
    image_only = io.BytesIO()
    blank.write(image_only)
    with pytest.raises(DocumentError, match="image-only"):
        pdf_document(image_only.getvalue(), "scan.pdf", "notice_pdf", "N1-")


def test_resume_audit_requires_resume_and_code_evidence_without_unsupported_rewrites(monkeypatch):
    fact_sheet = build_fact_sheet({
        "README.md": "# FastAPI example\n",
        "app.py": "from fastapi import FastAPI\napp = FastAPI()\n@app.get('/health')\ndef health(): return {'ok': True}\n",
    }, [], {"full_name": "demo/repo", "commit_sha": "abc123", "url": "https://github.com/demo/repo"}, 2)
    resume = text_document("resume", "Built a FastAPI service.\nServed 10,000 users.", "resume_text", "R", resume=True)
    resume_line_one = resume["evidence"][0]["id"]
    resume_line_two = resume["evidence"][1]["id"]
    repo_evidence = next(item for item in fact_sheet["evidence"] if item["path"] == "app.py")
    response = {
        "summary": "One project claim is supported; user scale was not found in this scan.",
        "claims": [
            {"claim": "Built a FastAPI service.", "resume_evidence_ids": [resume_line_one], "status": "supported",
             "repo_evidence_ids": [repo_evidence["id"]], "rationale": "The app imports and initializes FastAPI.",
             "defensible_rewrite": "Built a FastAPI service."},
            {"claim": "Served 10,000 users.", "resume_evidence_ids": [resume_line_two], "status": "not_found_in_scanned_scope",
             "repo_evidence_ids": [], "rationale": "The scanned files do not show user counts.", "defensible_rewrite": ""},
        ],
        "_model_provider": "gemini",
    }
    monkeypatch.setattr(document_analyzers, "_request_model", lambda *args, **kwargs: dict(response))
    result = document_analyzers.audit_resume(fact_sheet, resume)
    assert [claim["status"] for claim in result["claims"]] == ["supported", "not_found_in_scanned_scope"]
    assert result["claims"][1]["defensible_rewrite"] == ""

    bad = dict(response)
    bad["claims"] = [dict(response["claims"][1], defensible_rewrite="Led 10,000 users to success.")]
    monkeypatch.setattr(document_analyzers, "_request_model", lambda *args, **kwargs: dict(bad))
    with pytest.raises(ModelError, match="unsupported claim was given a stronger rewrite"):
        document_analyzers.audit_resume(fact_sheet, resume)


def test_notice_compare_validates_changes_conflicts_and_action_date(monkeypatch):
    earlier = text_document("Original notice", "Deadline: 2026-11-10", "notice_text", "N1-")
    later = text_document("Updated notice", "Deadline: 2026-11-12", "notice_text", "N2-")
    ids = [earlier["evidence"][0]["id"], later["evidence"][0]["id"]]
    mocked = {
        "summary": "The deadline moved two days later.",
        "notice_facts": [{"notice_name": "Updated notice", "topic": "deadline", "value": "2026-11-12", "evidence_ids": [ids[1]]}],
        "changes": [{"topic": "deadline", "earlier_value": "2026-11-10", "later_value": "2026-11-12", "status": "changed", "evidence_ids": ids}],
        "conflicts": [{"topic": "deadline", "details": "The two notices list different deadlines.", "evidence_ids": ids}],
        "actions": [{"action": "Submit the application", "due_date": "2026-11-12", "evidence_ids": [ids[1]]}],
        "_model_provider": "gemini",
    }
    monkeypatch.setattr(document_analyzers, "_request_model", lambda *args, **kwargs: dict(mocked))
    result = document_analyzers.analyze_notices([earlier, later])
    assert result["changes"][0]["status"] == "changed"
    assert result["conflicts"] and result["actions"][0]["due_date"] == "2026-11-12"
    assert result["model_provider"] == "gemini"
