# BuildProof

Evidence for your next move.

BuildProof helps students prepare for judges, support resume claims with project evidence, and stay on top of changing campus notices. Each mode attaches citations to its source material and verifies references before showing a result.

## Modes

- **Defend a repo:** Scan a public GitHub repository for its stack, routes, entry points, integrations, documentation signals, and likely secrets. Get an architecture overview, five judge questions, and a three-question practice round.
- **Prove resume claims:** Compare pasted resume text or a text-based PDF with one public GitHub repository. Claims are marked supported, partly supported, or not found in scanned scope; suggested wording never adds unsupported facts or metrics.
- **Track campus notices:** Paste notice text or upload text-based PDFs. Extract deadlines only when the cited text supports the date, compare documents in the order provided, flag changes and conflicts with source evidence, and export dated actions as an `.ics` calendar file.

All modes use a shared evidence registry. Repository citations point to file lines; document citations point to source name, page, and line. BharatCode Qwen 3.8 27B is tried first, with Google Gemini 3.5 Flash-Lite as fallback. Configure `GEMINI_API_KEY` to enable fallback, or use Gemini alone by leaving `BHARATCODE_API_KEY` empty.

## Run locally

Python 3.11+ and Node.js 20.19+ (or 22.12+) are recommended.

Backend:

```bash
cd backend
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
BHARATCODE_API_KEY=your_key GEMINI_API_KEY=your_google_ai_key GITHUB_TOKEN=your_read_only_token .venv/bin/uvicorn app.main:app --reload --port 8000
```

Frontend, in a second terminal:

```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:5173. Vite proxies `/api` to FastAPI on port 8000. `/api/sample` does not require model or GitHub credentials.

Copy `.env.example` for variable names. Keep credentials in environment variables or a secret store; never commit them. The GitHub token needs read-only public repository access and stays on the backend.

## Deploy

1. Deploy `frontend/` as a Vercel Vite app (`npm run build`, output `dist`). Set `VITE_API_BASE_URL` to the Render API origin.
2. Deploy `render.yaml` as a single-instance Render web service with one Uvicorn worker.
3. Configure `GITHUB_TOKEN`, at least one of `BHARATCODE_API_KEY` or `GEMINI_API_KEY`, and `FRONTEND_ORIGIN` in Render. `GEMINI_MODEL` defaults to `gemini-3.5-flash-lite`.

Render free services can spin down. In-memory jobs and caches are lost on restart; users can retry after a lost job.

## Limits and privacy

- Repository analysis accepts public GitHub repositories only. Archives are capped at 20 MB compressed and 10 MB uncompressed; at most 300 text files and 256 KB per file are scanned.
- Resume mode uses one public repository. Pasted documents are limited to 50,000 characters. PDFs must contain selectable text and be at most 5 MB and 25 pages. Image-only PDFs are not OCR'd.
- Notice mode accepts up to five documents per analysis, with the same text and PDF limits. Requests declaring more than 28 MB are rejected before parsing. It compares only the notices submitted by the user; it does not monitor campus sites.
- Submitted resume and notice text, plus selected repository evidence, are sent to the configured model provider. The UI discloses this before submission. BuildProof does not write these documents to a database or hosted report; extracted evidence and results remain temporarily in backend process memory for job retrieval.
- Resume email and phone patterns and likely code secrets are redacted before model use. Detection is heuristic. Review exported excerpts before sharing.
- Source code is treated as untrusted text and is never executed. Model outputs must pass citation validation before display.
- Successful repo reports are cached in process memory for six hours (up to 100 reports). Resume and notice analyses are not added to that report cache.

## API

- `POST /api/analyze` — JSON `{ "repo_url": "https://github.com/owner/repo" }`.
- `POST /api/resume-audit` — `multipart/form-data` with `repo_url` and exactly one of `resume_text` or `resume_pdf`.
- `POST /api/notices/analyze` — `multipart/form-data` with optional `notice_texts` (JSON list of `{ "name", "text" }`) and/or repeated `notice_pdfs` files.
- All analysis endpoints return `202` with `{ "job_id", "poll_url", "cache_hit" }`; poll `GET /api/jobs/{job_id}` for progress and the mode-specific result.
- `POST /api/practice` — submit an answer to one of the cached Repo Defense questions.
- `GET /api/sample` and `GET /api/health` — sample repo report and service status.

## Checks

```bash
cd backend && .venv/bin/pytest -q
cd frontend && npm test
cd frontend && npm run build
```
