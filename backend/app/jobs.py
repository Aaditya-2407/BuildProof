from __future__ import annotations

import asyncio
import time
import uuid
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Any

from .analyzer import build_report, evaluate_practice, evaluate_sample_practice
from .document_analyzers import analyze_notices, audit_resume
from .scanner import RepoRef, fetch_archive, scan_archive

REPORT_TTL_SECONDS = 6 * 60 * 60
HEAD_TTL_SECONDS = 5 * 60
JOB_TTL_SECONDS = 30 * 60
MAX_CACHED_REPORTS = 100
MAX_JOBS = 300
MAX_CONCURRENT_ANALYSES = 2


@dataclass
class Job:
    id: str
    kind: str
    status: str = "queued"
    stage: str = "queued"
    created_at: float = field(default_factory=time.monotonic)
    result: dict[str, Any] | None = None
    error: str | None = None
    cache_hit: bool = False
    repo_key: str | None = None

    def public(self) -> dict[str, Any]:
        body: dict[str, Any] = {"job_id": self.id, "status": self.status, "stage": self.stage,
                                "cache_hit": self.cache_hit}
        if self.result is not None:
            body["result"] = self.result
        if self.error:
            body["error"] = self.error
        return body


JOBS: OrderedDict[str, Job] = OrderedDict()
REPORT_CACHE: OrderedDict[str, tuple[float, dict[str, Any]]] = OrderedDict()
HEAD_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}
IN_FLIGHT: dict[str, asyncio.Task] = {}
KEY_JOBS: dict[str, set[str]] = {}
REF_IN_FLIGHT: dict[str, asyncio.Task] = {}
REF_JOBS: dict[str, set[str]] = {}
SEMAPHORE = asyncio.Semaphore(MAX_CONCURRENT_ANALYSES)
LOCK = asyncio.Lock()


def _new_job(kind: str, repo_key: str | None = None) -> Job:
    job = Job(id=uuid.uuid4().hex, kind=kind, repo_key=repo_key)
    JOBS[job.id] = job
    while len(JOBS) > MAX_JOBS:
        JOBS.popitem(last=False)
    return job


def _prune() -> None:
    now = time.monotonic()
    for key, (created, _) in list(REPORT_CACHE.items()):
        if now - created > REPORT_TTL_SECONDS:
            REPORT_CACHE.pop(key, None)
    for key, (created, _) in list(HEAD_CACHE.items()):
        if now - created > HEAD_TTL_SECONDS:
            HEAD_CACHE.pop(key, None)
    for key, job in list(JOBS.items()):
        if now - job.created_at > JOB_TTL_SECONDS and job.status in {"completed", "failed"}:
            JOBS.pop(key, None)


async def resolve_head(ref: RepoRef) -> dict[str, Any]:
    from .scanner import resolve_head as fetch_head
    async with LOCK:
        _prune()
        cached = HEAD_CACHE.get(ref.key)
        if cached:
            return cached[1]
    result = await asyncio.to_thread(fetch_head, ref)
    async with LOCK:
        HEAD_CACHE[ref.key] = (time.monotonic(), result)
    return result


async def start_analysis(ref: RepoRef) -> Job:
    async with LOCK:
        _prune()
        job = _new_job("analysis", ref.key)
        job.status = "running"
        job.stage = "resolving_repository"
        REF_JOBS.setdefault(ref.key, set()).add(job.id)
        if ref.key not in REF_IN_FLIGHT:
            REF_IN_FLIGHT[ref.key] = asyncio.create_task(_resolve_and_start(ref))
        return job


async def start_resume_audit(ref: RepoRef, resume: dict[str, Any]) -> Job:
    async with LOCK:
        _prune()
        job = _new_job("resume", ref.key)
        job.status = "running"
        job.stage = "resolving_repository"
        asyncio.create_task(_run_resume_audit(job.id, ref, resume))
        return job


async def start_notice_analysis(documents: list[dict[str, Any]]) -> Job:
    async with LOCK:
        _prune()
        job = _new_job("notices")
        job.status = "running"
        job.stage = "extracting_notice_facts"
        asyncio.create_task(_run_notice_analysis(job.id, documents))
        return job


async def _complete_transient_job(job_id: str, *, result: dict[str, Any] | None = None, error: str | None = None) -> None:
    async with LOCK:
        current = JOBS.get(job_id)
        if current:
            current.status = "failed" if error else "completed"
            current.stage = "failed" if error else "complete"
            if error:
                current.error = error
            else:
                current.result = result


async def _run_resume_audit(job_id: str, ref: RepoRef, resume: dict[str, Any]) -> None:
    try:
        async with SEMAPHORE:
            await _set_transient_stage(job_id, "resolving_repository")
            from .scanner import resolve_head as fetch_head
            meta = await asyncio.to_thread(fetch_head, ref)
            await _set_transient_stage(job_id, "fetching_archive")
            archive = await asyncio.to_thread(fetch_archive, meta)
            await _set_transient_stage(job_id, "scanning_files")
            fact_sheet = await asyncio.to_thread(scan_archive, archive, meta)
            await _set_transient_stage(job_id, "matching_resume_claims")
            result = await asyncio.to_thread(audit_resume, fact_sheet, resume)
        await _complete_transient_job(job_id, result=result)
    except Exception as exc:
        await _complete_transient_job(job_id, error=str(exc) or "Resume audit failed.")


async def _run_notice_analysis(job_id: str, documents: list[dict[str, Any]]) -> None:
    try:
        async with SEMAPHORE:
            await _set_transient_stage(job_id, "analyzing_notices")
            result = await asyncio.to_thread(analyze_notices, documents)
        await _complete_transient_job(job_id, result=result)
    except Exception as exc:
        await _complete_transient_job(job_id, error=str(exc) or "Notice analysis failed.")


async def _set_transient_stage(job_id: str, stage: str) -> None:
    async with LOCK:
        job = JOBS.get(job_id)
        if job:
            job.stage = stage


async def _resolve_and_start(ref: RepoRef) -> None:
    try:
        meta = await resolve_head(ref)
        key = f"{meta['full_name'].lower()}@{meta['commit_sha']}"
        async with LOCK:
            # Transfer every request queued for this repository and release the
            # lookup slot in the same critical section. A new request arriving
            # after this point will start its own lookup and then join by SHA.
            job_ids = REF_JOBS.pop(ref.key, set())
            REF_IN_FLIGHT.pop(ref.key, None)
            cached = REPORT_CACHE.get(key)
            if cached:
                REPORT_CACHE.move_to_end(key)
                for job_id in job_ids:
                    job = JOBS.get(job_id)
                    if job:
                        job.status, job.stage = "completed", "complete"
                        job.result, job.cache_hit = cached[1], True
                return
            KEY_JOBS.setdefault(key, set()).update(job_ids)
            if key not in IN_FLIGHT:
                IN_FLIGHT[key] = asyncio.create_task(_run_analysis(key, meta))
            else:
                for job_id in job_ids:
                    job = JOBS.get(job_id)
                    if job:
                        job.stage = "joining_existing_analysis"
    except Exception as exc:
        async with LOCK:
            for job_id in REF_JOBS.pop(ref.key, set()):
                job = JOBS.get(job_id)
                if job:
                    job.status, job.stage, job.error = "failed", "failed", str(exc) or "Could not resolve repository."
            REF_IN_FLIGHT.pop(ref.key, None)


async def _set_jobs(key: str, *, status: str | None = None, stage: str | None = None,
                    result: dict[str, Any] | None = None, error: str | None = None) -> None:
    async with LOCK:
        for job_id in list(KEY_JOBS.get(key, set())):
            job = JOBS.get(job_id)
            if not job:
                continue
            if status is not None:
                job.status = status
            if stage is not None:
                job.stage = stage
            if result is not None:
                job.result = result
            if error is not None:
                job.error = error


async def _run_analysis(key: str, meta: dict[str, Any]) -> None:
    try:
        async with SEMAPHORE:
            await _set_jobs(key, status="running", stage="fetching_archive")
            archive = await asyncio.to_thread(fetch_archive, meta)
            await _set_jobs(key, stage="scanning_files")
            fact_sheet = await asyncio.to_thread(scan_archive, archive, meta)
            await _set_jobs(key, stage="building_grounded_report")
            report = await asyncio.to_thread(build_report, fact_sheet)
            async with LOCK:
                REPORT_CACHE[key] = (time.monotonic(), report)
                REPORT_CACHE.move_to_end(key)
                while len(REPORT_CACHE) > MAX_CACHED_REPORTS:
                    REPORT_CACHE.popitem(last=False)
            await _set_jobs(key, status="completed", stage="complete", result=report)
    except Exception as exc:  # surface a short, actionable error to the client
        await _set_jobs(key, status="failed", stage="failed", error=str(exc) or "Analysis failed.")
    finally:
        async with LOCK:
            IN_FLIGHT.pop(key, None)
            KEY_JOBS.pop(key, None)


async def start_practice(
    question: dict[str, Any], answer: str, evidence: list[dict[str, Any]], *,
    is_sample: bool = False, preferred_provider: str | None = None,
) -> Job:
    _prune()
    job = _new_job("practice")
    job.status = "running"
    job.stage = "reviewing_answer"
    asyncio.create_task(_run_practice(job.id, question, answer, evidence, is_sample, preferred_provider))
    return job


async def get_cached_report(full_name: str, commit_sha: str) -> dict[str, Any] | None:
    key = f"{full_name.lower()}@{commit_sha}"
    async with LOCK:
        _prune()
        item = REPORT_CACHE.get(key)
        if not item:
            return None
        REPORT_CACHE.move_to_end(key)
        return item[1]


async def _run_practice(
    job_id: str, question: dict[str, Any], answer: str, evidence: list[dict[str, Any]],
    is_sample: bool, preferred_provider: str | None,
) -> None:
    job = JOBS.get(job_id)
    if not job:
        return
    try:
        if is_sample:
            result = evaluate_sample_practice(question, evidence)
        else:
            async with SEMAPHORE:
                result = await asyncio.to_thread(
                    evaluate_practice, question, answer, evidence, preferred_provider=preferred_provider
                )
        async with LOCK:
            current = JOBS.get(job_id)
            if current:
                current.status = "completed"
                current.stage = "complete"
                current.result = result
    except Exception as exc:
        async with LOCK:
            current = JOBS.get(job_id)
            if current:
                current.status = "failed"
                current.stage = "failed"
                current.error = str(exc) or "Practice feedback failed."


async def get_job(job_id: str) -> Job | None:
    async with LOCK:
        _prune()
        return JOBS.get(job_id)


def reset_state_for_tests() -> None:
    JOBS.clear()
    REPORT_CACHE.clear()
    HEAD_CACHE.clear()
    IN_FLIGHT.clear()
    KEY_JOBS.clear()
    REF_IN_FLIGHT.clear()
    REF_JOBS.clear()
