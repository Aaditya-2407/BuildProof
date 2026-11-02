from __future__ import annotations

import io
import zipfile

from app.scanner import scan_archive


def test_sparse_rust_repository_is_scanned_as_other_with_visible_scope_note():
    archive_bytes = io.BytesIO()
    with zipfile.ZipFile(archive_bytes, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("rust-project-main/src/main.rs", "fn main() {\n    println!(\"hello\");\n}\n")

    fact_sheet = scan_archive(archive_bytes.getvalue(), {
        "full_name": "demo/rust-project", "commit_sha": "abc123", "url": "https://github.com/demo/rust-project",
    })

    assert fact_sheet["scan"]["languages_detected"] == ["Rust"]
    assert any(item["path"] == "src/main.rs" and item["kind"] == "code_signal" for item in fact_sheet["evidence"])
    assert any("No Flask, FastAPI, or Express routes" in note for note in fact_sheet["scan"]["coverage_notes"])
