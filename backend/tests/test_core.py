from __future__ import annotations

import io
import zipfile

import pytest

from app.analyzer import validate_citations
from app import analyzer
from app.scanner import ScanError, build_fact_sheet, model_safe_fact_sheet, parse_repo_url, redact_secret_values, scan_archive


def test_citation_validator_accepts_only_known_source_ranges():
    evidence = {"E0001": {"id": "E0001", "path": "main.py", "line_start": 2, "line_end": 3, "line_count": 3, "excerpt": "x = 1"}}
    assert validate_citations({"evidence_ids": ["E0001"]}, evidence) == (True, None)
    valid, error = validate_citations({"evidence_ids": ["E9999"]}, evidence)
    assert not valid
    assert "Unknown evidence ID" in (error or "")
    valid, error = validate_citations({"evidence_ids": ["E0001"]}, {"E0001": {**evidence["E0001"], "line_end": 4}})
    assert not valid
    assert "Invalid source range" in (error or "")

    for citation_field in ("resume_evidence_ids", "repo_evidence_ids", "documentation_evidence_ids", "code_evidence_ids"):
        valid, error = validate_citations({citation_field: ["E9999"]}, evidence)
        assert not valid
        assert "Unknown evidence ID" in (error or "")


def test_secret_values_are_redacted_from_browser_and_model_material():
    secret = "super_secret_token_value_4815162342"
    fact_sheet = build_fact_sheet({".env": f"API_TOKEN={secret}\n"}, [], {
        "full_name": "demo/private-looking-public", "commit_sha": "abc123", "url": "https://github.com/demo/repo"
    }, 1)
    safe = model_safe_fact_sheet(fact_sheet)
    assert secret not in str(safe)
    assert secret not in str(fact_sheet["secret_findings"])
    assert fact_sheet["secret_findings"]
    assert "[REDACTED]" in fact_sheet["secret_findings"][0]["redacted_excerpt"]
    assert secret not in redact_secret_values(f"TOKEN={secret}")
    assert "sk-live-example-key-value-1234567890" not in redact_secret_values("API_KEY=sk-live-example-key-value-1234567890")
    assert "private-key-material" not in redact_secret_values("-----BEGIN PRIVATE KEY-----\nprivate-key-material")


def test_archive_filtering_skips_lockfiles_vendor_and_unsafe_paths():
    data = io.BytesIO()
    with zipfile.ZipFile(data, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("repo-main/README", "Hello from an extensionless README.\n")
        archive.writestr("repo-main/app.py", "from flask import Flask\napp = Flask(__name__)\n@app.get('/health')\ndef health(): return {'ok': True}\n")
        archive.writestr("repo-main/package-lock.json", "{}")
        archive.writestr("repo-main/node_modules/pkg/index.js", "not scanned")
        archive.writestr("repo-main/../escape.py", "print('unsafe')")
    result = scan_archive(data.getvalue(), {"full_name": "demo/repo", "commit_sha": "abc", "url": "https://github.com/demo/repo"})
    paths = {item["path"] for item in result["evidence"]}
    assert any(path == "README" for path in paths)
    assert any(path == "app.py" for path in paths)
    assert not any("node_modules" in path or "package-lock" in path for path in paths)
    assert any(item["reason"] == "unsafe_path" for item in result["scan"]["files_skipped"])


def test_repo_url_parser_rejects_malformed_hosts_and_embedded_credentials():
    assert parse_repo_url("https://github.com/owner/repo.git").key == "owner/repo"
    with pytest.raises(ScanError, match="valid public GitHub"):
        parse_repo_url("https://[::1/owner/repo")
    with pytest.raises(ScanError, match="without embedded credentials"):
        parse_repo_url("https://student:token@github.com/owner/repo")


def test_gemini_is_used_when_bharatcode_generation_fails(monkeypatch):
    monkeypatch.setenv("BHARATCODE_API_KEY", "configured")
    monkeypatch.setenv("GEMINI_API_KEY", "configured")

    def unavailable(*args, **kwargs):
        raise analyzer.ModelError("BharatCode account has no generation access.")

    monkeypatch.setattr(analyzer, "_request_bharatcode", unavailable)
    monkeypatch.setattr(analyzer, "_request_gemini", lambda *args, **kwargs: {"result": "ok"})
    result = analyzer._request_model("prompt", "test", {"type": "object"})

    assert result == {"result": "ok", "_model_provider": "gemini"}
