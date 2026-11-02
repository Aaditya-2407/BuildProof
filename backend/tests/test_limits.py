from __future__ import annotations

from app.main import MAX_REQUEST_BODY_BYTES, _content_length_rejection


def test_content_length_limit_allows_valid_uploads_and_rejects_oversized_requests():
    assert _content_length_rejection(None) is None
    assert _content_length_rejection(str(MAX_REQUEST_BODY_BYTES)) is None
    oversized = _content_length_rejection(str(MAX_REQUEST_BODY_BYTES + 1))
    assert oversized is not None and oversized.status_code == 413
    assert "28 MB" in oversized.body.decode()
    cors_response = _content_length_rejection(str(MAX_REQUEST_BODY_BYTES + 1), "http://localhost:5173")
    assert cors_response is not None
    assert cors_response.headers["access-control-allow-origin"] == "http://localhost:5173"


def test_content_length_limit_rejects_malformed_or_negative_headers():
    for value in ("not-a-number", "-1"):
        rejected = _content_length_rejection(value)
        assert rejected is not None and rejected.status_code == 400
