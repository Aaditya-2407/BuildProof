from __future__ import annotations

import re
import os
import asyncio
import json

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from .analyzer import sample_report
from .documents import DocumentError, MAX_NOTICE_DOCUMENTS, pdf_document, text_document
from .jobs import get_cached_report, get_job, start_analysis, start_notice_analysis, start_practice, start_resume_audit
from .scanner import ScanError, parse_repo_url

app = FastAPI(title="BuildProof", version="0.2.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173", os.getenv("FRONTEND_ORIGIN", "https://buildproof.vercel.app")],
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["content-type"],
)


class AnalyzeRequest(BaseModel):
    repo_url: str = Field(min_length=1, max_length=500)


class PracticeRequest(BaseModel):
    full_name: str = Field(min_length=3, max_length=200)
    commit_sha: str = Field(min_length=3, max_length=64)
    question_index: int = Field(ge=0, le=4)
    is_sample: bool = False
    answer: str = Field(min_length=1, max_length=5000)


@app.get("/api/health")
def health():
    providers = []
    if os.getenv("BHARATCODE_API_KEY"):
        providers.append("bharatcode")
    if os.getenv("GEMINI_API_KEY"):
        providers.append("gemini")
    return {"ok": True, "model_configured": bool(providers), "model_providers": providers,
            "github_configured": bool(os.getenv("GITHUB_TOKEN"))}


@app.post("/api/analyze", status_code=202)
async def analyze(body: AnalyzeRequest):
    try:
        ref = parse_repo_url(body.repo_url)
        job = await start_analysis(ref)
    except ScanError as exc:
        raise HTTPException(400, str(exc)) from None
    return {"job_id": job.id, "poll_url": f"/api/jobs/{job.id}", "cache_hit": job.cache_hit}


@app.post("/api/resume-audit", status_code=202)
async def resume_audit(
    repo_url: str = Form(..., min_length=1, max_length=500),
    resume_text: str | None = Form(default=None),
    resume_pdf: UploadFile | None = File(default=None),
):
    if bool(resume_text and resume_text.strip()) == bool(resume_pdf):
        raise HTTPException(400, "Provide exactly one of resume_text or resume_pdf.")
    try:
        ref = parse_repo_url(repo_url)
        if resume_pdf:
            data = await resume_pdf.read(5 * 1024 * 1024 + 1)
            resume = await asyncio.to_thread(pdf_document, data, resume_pdf.filename or "resume.pdf", "resume_pdf", "R", resume=True)
        else:
            resume = text_document("Resume text", resume_text or "", "resume_text", "R", resume=True)
        job = await start_resume_audit(ref, resume)
    except (ScanError, DocumentError) as exc:
        raise HTTPException(400, str(exc)) from None
    return {"job_id": job.id, "poll_url": f"/api/jobs/{job.id}", "cache_hit": False}


@app.post("/api/notices/analyze", status_code=202)
async def notices_analyze(
    notice_texts: str | None = Form(default=None),
    notice_pdfs: list[UploadFile] | None = File(default=None),
):
    documents = []
    try:
        if notice_texts and notice_texts.strip():
            parsed = json.loads(notice_texts)
            if not isinstance(parsed, list):
                raise DocumentError("notice_texts must be a JSON list of objects with name and text fields.")
            if len(parsed) > MAX_NOTICE_DOCUMENTS:
                raise DocumentError("Compare no more than five notices at a time.")
            for index, item in enumerate(parsed, 1):
                if not isinstance(item, dict) or not isinstance(item.get("text"), str):
                    raise DocumentError("Each pasted notice needs text and may include a name.")
                name = str(item.get("name") or f"Notice {index}")[:120]
                documents.append(text_document(name, item["text"], "notice_text", f"N{index}-"))
        for upload in notice_pdfs or []:
            if len(documents) >= MAX_NOTICE_DOCUMENTS:
                raise DocumentError("Compare no more than five notices at a time.")
            data = await upload.read(5 * 1024 * 1024 + 1)
            index = len(documents) + 1
            doc = await asyncio.to_thread(pdf_document, data, upload.filename or f"notice-{index}.pdf", "notice_pdf", f"N{index}-")
            documents.append(doc)
        if not documents:
            raise DocumentError("Add pasted notice text or upload at least one PDF.")
        job = await start_notice_analysis(documents)
    except json.JSONDecodeError:
        raise HTTPException(400, "notice_texts must be valid JSON.") from None
    except DocumentError as exc:
        raise HTTPException(400, str(exc)) from None
    return {"job_id": job.id, "poll_url": f"/api/jobs/{job.id}", "cache_hit": False}


@app.get("/api/jobs/{job_id}")
async def job_status(job_id: str):
    if not re.fullmatch(r"[0-9a-f]{32}", job_id):
        raise HTTPException(404, "Job not found. The service may have restarted; submit this analysis again.")
    job = await get_job(job_id)
    if not job:
        raise HTTPException(404, "Job not found. The service may have restarted; submit this analysis again.")
    return job.public()


@app.post("/api/practice", status_code=202)
async def practice(body: PracticeRequest):
    if body.is_sample:
        report = sample_report()
        if body.full_name != report["repository"]["full_name"] or body.commit_sha != report["repository"]["commit_sha"]:
            raise HTTPException(400, "Sample report reference is invalid.")
    else:
        report = await get_cached_report(body.full_name, body.commit_sha)
        if report is None:
            raise HTTPException(410, "This analysis is no longer in memory. Re-analyze the repository before practicing.")
    questions = report.get("judge_questions", [])
    if body.question_index >= len(questions):
        raise HTTPException(400, "Question index is not present in this report.")
    question = questions[body.question_index]
    allowed_ids = set(question.get("evidence_ids", []))
    evidence = [item for item in report.get("evidence", []) if item.get("id") in allowed_ids]
    if not evidence:
        raise HTTPException(400, "This question has no verifiable source evidence.")
    job = await start_practice(
        question, body.answer, evidence, is_sample=body.is_sample,
        preferred_provider=report.get("model_provider"),
    )
    return {"job_id": job.id, "poll_url": f"/api/jobs/{job.id}", "cache_hit": False}


@app.get("/api/sample")
def sample():
    return sample_report()
