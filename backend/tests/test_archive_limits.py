from __future__ import annotations

import io
import zipfile

from app.scanner import scan_archive


META = {"full_name": "demo/archive-limits", "commit_sha": "abc123", "url": "https://github.com/demo/archive-limits"}


def test_archive_skips_oversized_and_extreme_compression_files():
    archive_bytes = io.BytesIO()
    with zipfile.ZipFile(archive_bytes, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("project-main/README.md", "A small project description.")
        archive.writestr("project-main/large.py", "".join(chr(32 + (i % 90)) for i in range(256 * 1024 + 1)))
        archive.writestr("project-main/compressed.py", "value = 1\n" * 4000)

    fact_sheet = scan_archive(archive_bytes.getvalue(), META)
    reasons = {item["path"]: item["reason"] for item in fact_sheet["scan"]["files_skipped"]}

    assert reasons["large.py"] == "file_over_256_kb"
    assert reasons["compressed.py"] == "compression_ratio_limit"
    assert not any(item["path"] in {"large.py", "compressed.py"} for item in fact_sheet["evidence"])
