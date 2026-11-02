from __future__ import annotations

import pytest

from app.documents import DocumentError, text_document


def test_resume_contact_details_are_redacted_and_paste_limit_is_enforced():
    resume = text_document(
        "resume",
        "Email: student@example.edu\nPhone: +91 98765 43210\nAPI_KEY=sk-live-example-key-value-1234567890",
        "resume_text", "R", resume=True,
    )
    excerpts = "\n".join(item["excerpt"] for item in resume["evidence"])
    assert "student@example.edu" not in excerpts
    assert "98765 43210" not in excerpts
    assert "sk-live-example-key-value-1234567890" not in excerpts
    assert "[EMAIL REDACTED]" in excerpts and "[PHONE REDACTED]" in excerpts

    with pytest.raises(DocumentError, match="50,000 characters"):
        text_document("resume", "x" * 50_001, "resume_text", "R", resume=True)
