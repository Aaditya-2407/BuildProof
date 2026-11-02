from __future__ import annotations

import io
import json
import os
import re
import copy
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Any


API_ROOT = "https://api.github.com"
MAX_ARCHIVE_COMPRESSED = 20 * 1024 * 1024
MAX_ARCHIVE_UNCOMPRESSED = 10 * 1024 * 1024
MAX_ELIGIBLE_FILES = 300
MAX_FILE_BYTES = 256 * 1024
MAX_ARCHIVE_ENTRIES = 5000

SKIP_DIRS = {
    ".git", ".next", ".nuxt", ".venv", "venv", "node_modules", "vendor",
    "dist", "build", "coverage", "target", "__pycache__", "out", "assets",
}
SKIP_FILES = {
    "package-lock.json", "pnpm-lock.yaml", "yarn.lock", "bun.lockb", "poetry.lock",
    "uv.lock", "pipfile.lock", "cargo.lock", "composer.lock", "gemfile.lock",
}
TEXT_SUFFIXES = {
    ".py", ".pyi", ".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx", ".json",
    ".toml", ".yaml", ".yml", ".md", ".txt", ".html", ".ini", ".cfg", ".env",
    ".example", ".sh", ".sql", ".xml", ".properties",
}
TEXT_NAMES = {
    "dockerfile", "makefile", "procfile", ".env", ".env.example", ".gitignore",
    "requirements.txt", "pyproject.toml", "package.json", "readme", "bharatcode.txt",
}
ENV_PATTERNS = (
    re.compile(r"\bos\.getenv\(\s*['\"]([A-Z][A-Z0-9_]*)['\"]"),
    re.compile(r"\bos\.environ(?:\.get)?\(\s*['\"]([A-Z][A-Z0-9_]*)['\"]"),
    re.compile(r"\bos\.environ\[\s*['\"]([A-Z][A-Z0-9_]*)['\"]\s*\]"),
    re.compile(r"\bprocess\.env\.([A-Z][A-Z0-9_]*)"),
    re.compile(r"\bprocess\.env\[\s*['\"]([A-Z][A-Z0-9_]*)['\"]\s*\]"),
    re.compile(r"\bimport\.meta\.env\.([A-Z][A-Z0-9_]*)"),
)

SECRET_PATTERNS = [
    ("private_key", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----")),
    ("github_token", re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9_]{20,}|github_pat_[A-Za-z0-9_]{20,})\b")),
    ("aws_access_key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("openai_style_key", re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b")),
    ("google_api_key", re.compile(r"\bAIza[0-9A-Za-z_-]{30,}\b")),
    ("slack_token", re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{20,}\b")),
    ("gitlab_token", re.compile(r"\bglpat-[A-Za-z0-9_-]{20,}\b")),
    ("generic_secret_assignment", re.compile(
        r"(?i)(\b[A-Z0-9_]*(?:API[_-]?KEY|API[_-]?TOKEN|SECRET(?:[_-]?KEY)?|PASSWORD|TOKEN|CREDENTIALS?|ACCESS[_-]?TOKEN|PRIVATE[_-]?KEY)\b\s*[:=]\s*['\"]?)[A-Za-z0-9_./+=-]{4,}"
    )),
    ("credential_url", re.compile(r"(?i)(\b(?:postgres(?:ql)?|mysql|mongodb(?:\+srv)?):\/\/[^:/@\s]+:)[^@\s]+(@)")),
]


def _redact_line(value: str) -> str:
    redacted = re.sub(r"\b(?:gh[pousr]_[A-Za-z0-9_]{20,}|github_pat_[A-Za-z0-9_]{20,}|AKIA[0-9A-Z]{16}|sk-[A-Za-z0-9_-]{20,}|AIza[0-9A-Za-z_-]{30,}|xox[baprs]-[A-Za-z0-9-]{20,}|glpat-[A-Za-z0-9_-]{20,})\b", "[REDACTED]", value)
    for label, pattern in SECRET_PATTERNS:
        if label == "generic_secret_assignment":
            redacted = pattern.sub(lambda match: match.group(1) + "[REDACTED]", redacted)
        elif label == "credential_url":
            redacted = pattern.sub(lambda match: match.group(1) + "[REDACTED]" + match.group(2), redacted)
        elif pattern.groups:
            redacted = pattern.sub("[REDACTED]", redacted)
        else:
            redacted = pattern.sub("[REDACTED]", redacted)
    return redacted[:240]


def redact_secret_values(value: str) -> str:
    redacted = value
    redacted = re.sub(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----.*?(?:-----END [A-Z ]*PRIVATE KEY-----|\Z)",
                      "[PRIVATE KEY REDACTED]", redacted, flags=re.S)
    redacted = re.sub(r"\b(?:gh[pousr]_[A-Za-z0-9_]{20,}|github_pat_[A-Za-z0-9_]{20,}|AKIA[0-9A-Z]{16}|sk-[A-Za-z0-9_-]{20,}|AIza[0-9A-Za-z_-]{30,}|xox[baprs]-[A-Za-z0-9-]{20,}|glpat-[A-Za-z0-9_-]{20,})\b", "[REDACTED]", redacted)
    for label, pattern in SECRET_PATTERNS:
        if label == "generic_secret_assignment":
            redacted = pattern.sub(lambda match: match.group(1) + "[REDACTED]", redacted)
        elif label == "credential_url":
            redacted = pattern.sub(lambda match: match.group(1) + "[REDACTED]" + match.group(2), redacted)
        elif label not in {"github_token", "aws_access_key", "private_key"}:
            redacted = pattern.sub("[REDACTED]", redacted)
    return redacted

DOC_CLAIMS = {
    "authentication": re.compile(r"(?i)\b(auth(?:entication|orization)?|JWT|OAuth|login|sign[- ]?in)\b"),
    "database": re.compile(r"(?i)\b(database|PostgreSQL|Postgres|MySQL|MongoDB|SQLite|Redis)\b"),
    "real_time": re.compile(r"(?i)\b(real[- ]?time|WebSocket|websocket|live updates)\b"),
    "ai_model": re.compile(r"(?i)\b(LLM|large language model|AI[- ]powered|OpenAI|Anthropic|BharatCode|Gemini|Claude|Qwen)\b"),
    "deployment": re.compile(r"(?i)\b(deploy(?:ment|ed)?|production|Vercel|Render|Docker|Kubernetes)\b"),
}
class ScanError(Exception):
    pass


class GitHubError(Exception):
    def __init__(self, message: str, status: int = 502):
        super().__init__(message)
        self.status = status


@dataclass(frozen=True)
class RepoRef:
    owner: str
    name: str

    @property
    def key(self) -> str:
        return f"{self.owner.lower()}/{self.name.lower()}"


def parse_repo_url(value: str) -> RepoRef:
    try:
        parsed = urllib.parse.urlparse(value.strip())
        hostname = parsed.hostname
    except ValueError:
        raise ScanError("Enter a valid public GitHub repository URL.") from None
    if parsed.scheme not in ("https", "http") or hostname not in ("github.com", "www.github.com"):
        raise ScanError("Enter a public GitHub repository URL, such as https://github.com/owner/repo.")
    if parsed.username is not None or parsed.password is not None:
        raise ScanError("Use a GitHub repository URL without embedded credentials.")
    parts = [p for p in parsed.path.strip("/").split("/") if p]
    if len(parts) != 2:
        raise ScanError("Use the main repository URL, not a file, branch, or pull request link.")
    owner, name = parts
    name = name.removesuffix(".git")
    if not re.fullmatch(r"[A-Za-z0-9_.-]{1,100}", owner) or not re.fullmatch(r"[A-Za-z0-9_.-]{1,100}", name):
        raise ScanError("That GitHub repository URL is not valid.")
    return RepoRef(owner, name)


def _headers(accept: str = "application/vnd.github+json") -> dict[str, str]:
    headers = {"Accept": accept, "User-Agent": "RepoDefenseCoach/0.1"}
    token = os.getenv("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _request(url: str, *, headers: dict[str, str] | None = None, timeout: int = 20, cap: int | None = None) -> bytes:
    request = urllib.request.Request(url, headers=headers or _headers())
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            if cap is not None:
                data = response.read(cap + 1)
                if len(data) > cap:
                    raise ScanError("The repository archive exceeds the 20 MB download limit.")
                return data
            return response.read()
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            raise GitHubError("Repository not found or not public.", 404) from None
        if exc.code in (401, 403, 429):
            retry = exc.headers.get("X-RateLimit-Reset") if exc.headers else None
            detail = "GitHub rate limit reached. Try again shortly."
            if retry:
                detail += f" The rate limit resets at {retry}."
            raise GitHubError(detail, 429) from None
        raise GitHubError(f"GitHub returned HTTP {exc.code} while reading the repository.", 502) from None
    except urllib.error.URLError as exc:
        raise GitHubError(f"Could not reach GitHub: {exc.reason}", 502) from None


def resolve_head(ref: RepoRef) -> dict[str, Any]:
    if not os.getenv("GITHUB_TOKEN"):
        raise GitHubError("The server GitHub read-only token is not configured.", 503)
    base = f"{API_ROOT}/repos/{urllib.parse.quote(ref.owner)}/{urllib.parse.quote(ref.name)}"
    repo = json.loads(_request(base))
    if repo.get("private"):
        raise GitHubError("Only public repositories are supported.", 400)
    branch = repo.get("default_branch")
    if not branch:
        raise GitHubError("This repository has no default branch.", 400)
    commit = json.loads(_request(f"{base}/commits/{urllib.parse.quote(branch, safe='')}"))
    sha = commit.get("sha")
    if not sha:
        raise GitHubError("GitHub did not return the latest commit SHA.", 502)
    return {
        "owner": repo.get("owner", {}).get("login", ref.owner),
        "name": repo.get("name", ref.name),
        "full_name": repo.get("full_name", f"{ref.owner}/{ref.name}"),
        "url": repo.get("html_url", f"https://github.com/{ref.owner}/{ref.name}"),
        "description": repo.get("description"),
        "default_branch": branch,
        "commit_sha": sha,
    }


def fetch_archive(meta: dict[str, Any]) -> bytes:
    owner, name, sha = meta["owner"], meta["name"], meta["commit_sha"]
    url = f"{API_ROOT}/repos/{urllib.parse.quote(owner)}/{urllib.parse.quote(name)}/zipball/{sha}"
    return _request(url, headers=_headers("application/vnd.github+json"), timeout=30, cap=MAX_ARCHIVE_COMPRESSED)


def _safe_path(name: str) -> str | None:
    path = PurePosixPath(name)
    if path.is_absolute() or ".." in path.parts or not path.parts:
        return None
    # GitHub ZIPs prepend one root folder; strip it for stable report paths.
    clean = "/".join(path.parts[1:])
    if not clean:
        return None
    return clean


def _eligible(path: str) -> bool:
    p = PurePosixPath(path)
    lowered_parts = {part.lower() for part in p.parts}
    if lowered_parts & SKIP_DIRS:
        return False
    if p.name.lower() in SKIP_FILES:
        return False
    if p.name.lower().endswith(".min.js") or p.name.lower().endswith(".map"):
        return False
    return p.suffix.lower() in TEXT_SUFFIXES or p.name.lower() in TEXT_NAMES or p.name.lower().startswith(".env.")


def _line_of(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def _line_excerpt(lines: list[str], line: int, max_chars: int = 240) -> str:
    return lines[line - 1].strip()[:max_chars] if 1 <= line <= len(lines) else ""


def scan_archive(archive: bytes, meta: dict[str, Any]) -> dict[str, Any]:
    if len(archive) > MAX_ARCHIVE_COMPRESSED:
        raise ScanError("The repository archive exceeds the 20 MB download limit.")
    try:
        zf = zipfile.ZipFile(io.BytesIO(archive))
    except (zipfile.BadZipFile, OSError):
        raise ScanError("GitHub returned an unreadable repository archive.") from None
    infos = zf.infolist()
    if len(infos) > MAX_ARCHIVE_ENTRIES:
        raise ScanError("The repository contains too many archive entries to scan safely.")
    total_uncompressed = sum(info.file_size for info in infos)
    if total_uncompressed > MAX_ARCHIVE_UNCOMPRESSED:
        raise ScanError("The repository expands beyond the 10 MB scan limit.")

    files: dict[str, str] = {}
    skipped: list[dict[str, Any]] = []
    eligible_seen = 0
    for info in infos:
        if info.is_dir():
            continue
        path = _safe_path(info.filename)
        if path is None:
            skipped.append({"path": info.filename[:160], "reason": "unsafe_path", "size_bytes": info.file_size})
            continue
        mode = (info.external_attr >> 16) & 0xFFFF
        if mode and (mode & 0o170000) == 0o120000:
            skipped.append({"path": path, "reason": "symlink", "size_bytes": info.file_size})
            continue
        if not _eligible(path):
            continue
        eligible_seen += 1
        if eligible_seen > MAX_ELIGIBLE_FILES:
            skipped.append({"path": path, "reason": "eligible_file_limit", "size_bytes": info.file_size})
            continue
        if info.file_size > MAX_FILE_BYTES:
            skipped.append({"path": path, "reason": "file_over_256_kb", "size_bytes": info.file_size})
            continue
        if info.file_size / max(info.compress_size, 1) > 100:
            skipped.append({"path": path, "reason": "compression_ratio_limit", "size_bytes": info.file_size})
            continue
        try:
            raw = zf.read(info)
        except (RuntimeError, zipfile.BadZipFile, OSError):
            skipped.append({"path": path, "reason": "archive_read_error", "size_bytes": info.file_size})
            continue
        if b"\x00" in raw:
            skipped.append({"path": path, "reason": "binary_content", "size_bytes": info.file_size})
            continue
        files[path] = raw.decode("utf-8", errors="replace")

    if not files:
        raise ScanError("No eligible text files were found in this repository.")
    discovered_files = sum(1 for info in infos if not info.is_dir())
    return build_fact_sheet(files, skipped, meta, discovered_files)


def build_fact_sheet(files: dict[str, str], skipped: list[dict[str, Any]], meta: dict[str, Any], files_discovered: int) -> dict[str, Any]:
    evidence: list[dict[str, Any]] = []

    def add_evidence(path: str, line_start: int, line_end: int | None, kind: str, extractor: str) -> str:
        lines = files[path].splitlines()
        line_end = line_end or line_start
        eid = f"E{len(evidence) + 1:04d}"
        start_index = max(0, line_start - 1)
        selected_lines = lines[start_index:min(len(lines), line_end)]
        excerpt_lines: list[str] = []
        in_private_key = False
        for prior in lines[:start_index]:
            if re.search(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----", prior):
                in_private_key = True
            elif in_private_key and "-----END " in prior and "PRIVATE KEY-----" in prior:
                in_private_key = False
        for line in selected_lines:
            if re.search(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----", line):
                in_private_key = True
                excerpt_lines.append("[PRIVATE KEY REDACTED]")
            elif in_private_key:
                if "-----END " in line and "PRIVATE KEY-----" in line:
                    in_private_key = False
                else:
                    excerpt_lines.append("[PRIVATE KEY REDACTED]")
            else:
                excerpt_lines.append(_redact_line(line))
        excerpt = "\n".join(excerpt_lines)[:500]
        item = {"id": eid, "path": path, "line_start": line_start, "line_end": line_end, "line_count": len(lines), "excerpt": excerpt,
                "kind": kind, "extractor": extractor}
        evidence.append(item)
        return eid

    stack: list[dict[str, Any]] = []
    entry_points: list[dict[str, Any]] = []
    routes: list[dict[str, Any]] = []
    env_vars: dict[str, list[str]] = {}
    integrations: dict[str, list[str]] = {}
    secrets: list[dict[str, Any]] = []
    docs: list[tuple[str, str]] = []
    languages: set[str] = set()
    coverage_notes: list[str] = []

    for path, text in files.items():
        suffix = PurePosixPath(path).suffix.lower()
        if suffix == ".py": languages.add("Python")
        elif suffix in {".js", ".jsx", ".mjs", ".cjs"}: languages.add("JavaScript")
        elif suffix in {".ts", ".tsx"}: languages.add("TypeScript")
        elif suffix in {".go", ".rs", ".java", ".php", ".rb", ".cs", ".cpp", ".c"}: languages.add("Other")

        name = PurePosixPath(path).name.lower()
        lines = text.splitlines()
        if name in {"readme.md", "readme.txt", "readme"} or suffix in {".md", ".txt"}:
            docs.append((path, text))

        # Secret patterns are reported as redacted locations only. No raw secret is retained in output.
        for line_num, line in enumerate(lines, 1):
            for label, pattern in SECRET_PATTERNS:
                match = pattern.search(line)
                if match:
                    if label == "generic_secret_assignment" and re.search(r"(?i)(your[_-]|example|placeholder|change[_-]?me|replace[_-]?me|xxxxx)", match.group(0)):
                        continue
                    eid = add_evidence(path, line_num, line_num, "secret_signal", "secret_patterns")
                    secrets.append({"path": path, "line": line_num, "kind": label,
                                    "redacted_excerpt": _redact_line(line),
                                    "evidence_ids": [eid]})
                    break

        # Package and framework facts are intentionally limited to recognizable manifests.
        if name == "package.json":
            try:
                manifest = json.loads(text)
                for scope_name in ("dependencies", "devDependencies"):
                    for pkg, version in manifest.get(scope_name, {}).items():
                        line = next((i for i, v in enumerate(lines, 1) if f'"{pkg}"' in v), 1)
                        eid = add_evidence(path, line, line, "dependency", "package_json")
                        stack.append({"name": pkg, "version": version,
                                      "scope": "runtime" if scope_name == "dependencies" else "development",
                                      "evidence_ids": [eid]})
                        if pkg in {"express", "openai", "@anthropic-ai/sdk", "@google/generative-ai", "@aws-sdk/client-bedrock-runtime", "@modelcontextprotocol/sdk"}:
                            integrations.setdefault(pkg, []).append(eid)
            except (json.JSONDecodeError, TypeError):
                coverage_notes.append(f"Could not parse {path} as JSON.")
        elif name == "requirements.txt":
            for i, line in enumerate(lines, 1):
                match = re.match(r"\s*([A-Za-z0-9_.-]+)\s*(?:==|>=|~=)\s*([^;\s]+)", line)
                if match:
                    pkg, version = match.groups()
                    eid = add_evidence(path, i, i, "dependency", "requirements_txt")
                    stack.append({"name": pkg, "version": version, "scope": "runtime", "evidence_ids": [eid]})
        elif name == "pyproject.toml":
            for i, line in enumerate(lines, 1):
                match = re.match(r"\s*([A-Za-z0-9_.-]+)\s*=\s*[\"']([^\"']+)[\"']", line)
                if match and any(key in "\n".join(lines[max(0, i-4):i]).lower() for key in ("dependencies", "project", "optional-dependencies")):
                    pkg, version = match.groups()
                    if pkg.lower() not in {"name", "version", "description", "requires-python"}:
                        eid = add_evidence(path, i, i, "dependency", "pyproject_toml")
                        stack.append({"name": pkg, "version": version, "scope": "runtime", "evidence_ids": [eid]})

        entry_names = {"main.py", "app.py", "server.py", "wsgi.py", "manage.py", "server.js", "index.js",
                       "index.ts", "main.ts", "main.tsx", "main.jsx", "app.ts", "app.tsx"}
        if name in entry_names or path.lower() in {"src/main.tsx", "src/main.jsx", "src/index.tsx", "src/index.jsx"}:
            eid = add_evidence(path, 1, min(8, max(1, len(lines))), "entry_point", "entrypoint_names")
            entry_points.append({"path": path, "kind": "application", "evidence_ids": [eid]})

        # Routes: Flask/FastAPI decorators, plus Express app/router calls.
        for i, line in enumerate(lines, 1):
            if suffix == ".py":
                match = re.search(r"@(?:\w+\.)?(get|post|put|patch|delete|options|head|route)\s*\(\s*['\"]([^'\"]+)", line, re.I)
                if match:
                    method, route_path = match.groups()
                    method = method.upper()
                    if method == "ROUTE":
                        methods = re.search(r"methods\s*=\s*\[([^]]+)\]", line)
                        method = ",".join(re.findall(r"['\"]([A-Za-z]+)['\"]", methods.group(1))) if methods else "GET"
                    eid = add_evidence(path, i, i, "route", "python_route_decorator")
                    routes.append({"method": method, "path": route_path, "handler": None, "framework": "Flask/FastAPI", "evidence_ids": [eid]})
            elif suffix in {".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx"}:
                match = re.search(r"\b(?:app|router)\.(get|post|put|patch|delete|options|head)\s*\(\s*['\"`]([^'\"`]+)", line, re.I)
                if match:
                    method, route_path = match.groups()
                    eid = add_evidence(path, i, i, "route", "express_route_call")
                    routes.append({"method": method.upper(), "path": route_path, "handler": None, "framework": "Express", "evidence_ids": [eid]})

            for pattern in ENV_PATTERNS:
                for match in pattern.finditer(line):
                    key = match.group(1)
                    if key not in env_vars:
                        env_vars[key] = []
                    if not env_vars[key]:
                        env_vars[key].append(add_evidence(path, i, i, "environment_variable", "environment_reference"))

            if suffix in {".py", ".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx", ".json", ".toml", ".yaml", ".yml", ".sh"}:
                for url in re.findall(r"https?://[A-Za-z0-9.-]+", line):
                    host = urllib.parse.urlparse(url).hostname or url
                    integrations.setdefault(host, []).append(add_evidence(path, i, i, "external_url", "url_literal"))

        # SDK names/import strings provide deterministic integration signals.
        for marker, integration in (("openai", "OpenAI SDK"), ("anthropic", "Anthropic SDK"),
                                    ("google.generativeai", "Google Generative AI SDK"),
                                    ("boto3", "AWS SDK"), ("sqlalchemy", "SQLAlchemy"),
                                    ("mongoose", "Mongoose"), ("prisma", "Prisma"),
                                    ("socket.io", "Socket.IO")):
            match = re.search(re.escape(marker), text, re.I)
            if match and integration not in integrations:
                line = _line_of(text, match.start())
                integrations[integration] = [add_evidence(path, line, line, "integration", "known_sdk_signal")]

    # Keep stack and integration inventories concise and deterministic.
    unique_stack: dict[tuple[str, str | None, str], dict[str, Any]] = {}
    for item in stack:
        unique_stack[(item["name"].lower(), item["version"], item["scope"])] = item
    stack = list(unique_stack.values())[:80]
    integration_items = [{"name": name, "evidence_ids": list(dict.fromkeys(ids))[:4]}
                         for name, ids in list(integrations.items())[:40]]
    env_items = [{"name": name, "required_signal": "unknown", "value_included": False,
                  "evidence_ids": ids} for name, ids in sorted(env_vars.items())]

    readme_path = next((p for p in files if PurePosixPath(p).name.lower() in {"readme.md", "readme.txt", "readme"}
                        and len(PurePosixPath(p).parts) == 1), None)
    readme = files.get(readme_path, "") if readme_path else ""
    root_names = {PurePosixPath(p).name.lower() for p in files if len(PurePosixPath(p).parts) == 1}
    readme_present = bool(readme_path)
    setup_present = bool(re.search(r"(?i)(install|setup|getting started|quickstart|npm run|uvicorn|python .*main|docker compose)", readme))
    docs_evidence = []
    if readme_path:
        doc_line = next((i for i, line in enumerate(readme.splitlines(), 1) if line.strip()), 1)
        docs_evidence.append(add_evidence(readme_path, doc_line, min(doc_line + 3, max(1, len(readme.splitlines()))), "documentation", "readme_presence"))
    template_markers = []
    for path, text in files.items():
        if PurePosixPath(path).suffix.lower() not in {".md", ".txt"}:
            continue
        for marker in ("Lorem ipsum", "TODO: add", "Your project name", "Replace this with", "Describe your project"):
            match = re.search(re.escape(marker), text, re.I)
            if match:
                line = _line_of(text, match.start())
                eid = add_evidence(path, line, line, "template_marker", "template_marker_scan")
                template_markers.append({"marker": marker, "path": path, "evidence_ids": [eid]})

    docs_text = [(path, text) for path, text in files.items() if PurePosixPath(path).suffix.lower() in {".md", ".txt"}]
    claim_checks = []
    claim_signal = {
        "authentication": re.compile(r"(?i)(jwt|oauth|authlib|passport|firebase/auth|clerk|supabase/auth|login)"),
        "database": re.compile(r"(?i)(sqlalchemy|mongoose|prisma|psycopg|sqlite3|pymongo|redis|DATABASE_URL|\.db\b)"),
        "real_time": re.compile(r"(?i)(websocket|socket\.io|socketio|EventSource|text/event-stream)"),
        "ai_model": re.compile(r"(?i)(openai|anthropic|google\.generativeai|genai|bharatcode|qwen|deepseek)"),
        "deployment": re.compile(r"(?i)(vercel\.json|render\.yaml|Dockerfile|fly\.toml|railway\.json|Procfile|cloudbuild)"),
    }
    for category, doc_pattern in DOC_CLAIMS.items():
        claim_ref = None
        for path, text in docs_text:
            match = doc_pattern.search(text)
            if match:
                line = _line_of(text, match.start())
                claim_ref = {"path": path, "line": line, "snippet": _redact_line(_line_excerpt(text.splitlines(), line))}
                break
        if not claim_ref:
            continue
        doc_eid = add_evidence(claim_ref["path"], claim_ref["line"], claim_ref["line"], "documented_claim", "claim_keyword_scan")
        code_eids = []
        for path, text in files.items():
            if path == claim_ref["path"] or PurePosixPath(path).suffix.lower() not in {".py", ".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx", ".json", ".toml", ".yaml", ".yml"}:
                continue
            match = claim_signal[category].search(text)
            if match and len(code_eids) < 3:
                line = _line_of(text, match.start())
                code_eids.append(add_evidence(path, line, line, "code_signal", "claim_signal_scan"))
        claim_checks.append({"category": category, "claim": claim_ref["snippet"],
                             "status": "evidence_found" if code_eids else "not_found_in_scanned_scope",
                             "documentation_evidence_ids": [doc_eid], "code_evidence_ids": code_eids,
                             "coverage_note": "Static signals only; this is not proof that the capability is absent."})

    if "Other" in languages:
        coverage_notes.append("Routes and environment references are only structurally scanned for Python, JavaScript, and TypeScript.")
    if not routes:
        coverage_notes.append("No Flask, FastAPI, or Express routes were recognized in the scanned files.")
    files_scanned = len(files)
    fact_sheet = {
        "schema_version": "1.0",
        "repository": meta,
        "scan": {"source": "github_zipball", "files_discovered": files_discovered, "files_scanned": files_scanned,
                 "files_skipped": skipped[:100], "languages_detected": sorted(languages), "coverage_notes": coverage_notes},
        "evidence": evidence,
        "stack": stack,
        "entry_points": entry_points,
        "routes": routes[:150],
        "environment_variables": env_items,
        "integrations": integration_items,
        "documentation_and_compliance": {
            "readme_present": readme_present,
            "setup_instructions_present": setup_present,
            "bharatcode_file_present": "bharatcode.txt" in root_names,
            "env_example_present": any(n in {".env.example", ".env.sample", ".env.template"} for n in root_names),
            "license_file_present": any(n.startswith("license") or n.startswith("copying") for n in root_names),
            "template_markers": template_markers[:20], "evidence_ids": docs_evidence,
        },
        "secret_findings": secrets[:100],
        "claim_checks": claim_checks,
    }
    # The model gets neither secret-like lines nor secret findings, even in redacted form.
    return fact_sheet


def model_safe_fact_sheet(fact_sheet: dict[str, Any]) -> dict[str, Any]:
    safe = copy.deepcopy({k: v for k, v in fact_sheet.items() if k != "secret_findings"})
    secret_paths = {item["path"] for item in fact_sheet.get("secret_findings", [])}
    safe["evidence"] = [e for e in safe["evidence"] if not (e["path"] in secret_paths and e["kind"] == "secret_signal")]
    removed_ids = {e["id"] for e in fact_sheet["evidence"] if e not in safe["evidence"]}
    # Remove secret evidence references from deterministic fields defensively.
    for collection_name in ("stack", "entry_points", "routes", "environment_variables", "integrations", "claim_checks"):
        for item in safe.get(collection_name, []):
            for key, value in list(item.items()):
                if key.endswith("evidence_ids") and isinstance(value, list):
                    item[key] = [eid for eid in value if eid not in removed_ids]
    return safe
