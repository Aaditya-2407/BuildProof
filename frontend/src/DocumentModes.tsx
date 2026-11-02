import { useState } from "react";
import { AlertTriangle, CalendarDays, CheckCircle2, ChevronDown, Download, FileText, LoaderCircle, LockKeyhole, Printer, RefreshCw, Sparkles, Upload } from "lucide-react";
import { api, type Evidence, type JobStatus, type NoticeAction, type NoticeReport, type ResumeAudit } from "./api";
import { buildCalendarIcs } from "./calendar";
import "./DocumentModes.css";

export type BuildMode = "repo" | "resume" | "notices";

const sleep = (ms: number) => new Promise((resolve) => window.setTimeout(resolve, ms));
const charCount = (text: string) => Array.from(text).length;
const stages: Record<string, string> = {
  queued: "In the queue", resolving_repository: "Finding the latest commit", fetching_archive: "Fetching the public source",
  scanning_files: "Reading the repository", matching_resume_claims: "Checking resume claims against code",
  extracting_notice_facts: "Reading notice sources", analyzing_notices: "Comparing dates and requirements",
  complete: "Ready",
};

async function pollJob(url: string, onStage: (stage: string) => void): Promise<JobStatus> {
  const start = Date.now();
  while (Date.now() - start < 4 * 60 * 1000) {
    const job = await api.poll(url);
    onStage(stages[job.stage] ?? job.stage.replaceAll("_", " "));
    if (job.status === "completed") return job;
    if (job.status === "failed") throw new Error(job.error ?? "The analysis failed. Try again.");
    await sleep(1500);
  }
  throw new Error("This is taking longer than expected. You can retry the analysis.");
}

function sourceLabel(item: Evidence) {
  const loc = item.page_number ? `p.${item.page_number}, line ${item.line_start}` : `line ${item.line_start}`;
  return `${item.source_name ?? item.path} · ${loc}${item.line_end > item.line_start ? `–${item.line_end}` : ""}`;
}

function EvidenceLinks({ ids, evidence }: { ids: string[]; evidence: Evidence[] }) {
  const items = ids.map((id) => evidence.find((item) => item.id === id)).filter((item): item is Evidence => Boolean(item));
  if (!items.length) return <small className="bp-no-evidence">No matching evidence was found in the scanned scope.</small>;
  return <div className="bp-citations">{items.map((item) => <a href={`#bp-evidence-${item.id}`} key={item.id} title={item.excerpt}><FileText size={12} />{sourceLabel(item)}</a>)}</div>;
}

function EvidencePanel({ evidence }: { evidence: Evidence[] }) {
  return <details className="bp-evidence"><summary><span><FileText size={15} /> Evidence library</span><span>{evidence.length} excerpts <ChevronDown size={14} /></span></summary><div className="bp-evidence-grid">{evidence.map((item) => <article id={`bp-evidence-${item.id}`} key={item.id}><header><b>{item.id}</b><code>{sourceLabel(item)}</code></header><pre>{item.excerpt}</pre></article>)}</div></details>;
}

function ProviderNote({ provider }: { provider: string }) {
  return <div className="bp-provider"><Sparkles size={13} /> Analysis by {provider === "gemini" ? "Google Gemini 3.5 Flash-Lite" : "BharatCode Qwen 3.8 27B"}</div>;
}

function DocumentProgress({ busy, stage, error, onRetry }: { busy: boolean; stage: string; error: string; onRetry: () => void }) {
  return <>{busy && <div className="job-progress" role="status"><LoaderCircle size={17} className="spin" /><span><strong>{stage || "Starting analysis"}</strong><small>Documents are processed in memory for this analysis.</small></span><span className="progress-pips"><i /><i /><i /></span></div>}{error && <div className="error-banner" role="alert"><AlertTriangle size={16} /><span>{error}</span><button onClick={onRetry}><RefreshCw size={14} /> Retry</button></div>}</>;
}

function ReportActions({ name, markdown, onCalendar }: { name: string; markdown: string; onCalendar?: () => void }) {
  const exportMarkdown = () => {
    downloadFile(name, markdown, "text/markdown;charset=utf-8");
  };
  return <div className="bp-report-actions">{onCalendar && <button className="secondary-button" onClick={onCalendar}><CalendarDays size={14} />Download calendar</button>}<button className="secondary-button" onClick={exportMarkdown}><Download size={14} />Export Markdown</button><button className="secondary-button" onClick={() => window.print()}><Printer size={14} />Print</button></div>;
}

export function ResumeMode() {
  const [repoUrl, setRepoUrl] = useState("");
  const [resumeText, setResumeText] = useState("");
  const [pdf, setPdf] = useState<File | undefined>();
  const [inputType, setInputType] = useState<"text" | "pdf">("text");
  const [result, setResult] = useState<ResumeAudit | null>(null);
  const [busy, setBusy] = useState(false);
  const [stage, setStage] = useState("");
  const [error, setError] = useState("");

  const run = async () => {
    setError(""); setResult(null); setBusy(true); setStage("Starting resume audit");
    try {
      const started = await api.resumeAudit(repoUrl.trim(), resumeText, inputType === "pdf" ? pdf : undefined);
      const completed = await pollJob(started.poll_url, setStage);
      setResult(completed.result as ResumeAudit);
      window.setTimeout(() => document.getElementById("resume-result")?.scrollIntoView({ behavior: "smooth", block: "start" }), 80);
    } catch (err) { setError(err instanceof Error ? err.message : "Resume audit failed."); }
    finally { setBusy(false); }
  };

  const demo = () => {
    setRepoUrl("https://github.com/nsidnev/fastapi-realworld-example-app"); setInputType("text"); setPdf(undefined);
    setResumeText("PROJECTS\n• Built a REST API with FastAPI and PostgreSQL, including authentication and validation.\n• Served 10,000 users with 99.9% uptime.\n• Added automated tests for API error responses.");
    setResult(null); setError("");
  };

  return <main className="bp-mode-page"><section className="bp-mode-hero"><div className="eyebrow"><span className="eyebrow-line" />RESUME PROOF · CODE-BACKED CLAIMS</div><h1>Make every bullet<br /><em>defensible.</em></h1><p>Compare one resume with one public repo. See what the code supports, what it partly supports, and what this scan cannot verify.</p><div className="bp-mode-tags"><span><CheckCircle2 size={13} /> Evidence-linked</span><span><LockKeyhole size={13} /> No saved resume</span></div></section>
    <section className="bp-form-card"><div className="bp-card-title"><span>01</span><div><h2>Add your source material</h2><p>One public repository and one resume.</p></div><button type="button" className="bp-example-button" onClick={demo}>Load example</button></div>
      <label htmlFor="resume-repo">PUBLIC GITHUB REPOSITORY</label><input id="resume-repo" className="bp-text-input" type="url" placeholder="https://github.com/owner/repository" value={repoUrl} onChange={(event) => setRepoUrl(event.target.value)} />
      <div className="bp-input-tabs"><button type="button" aria-pressed={inputType === "text"} className={inputType === "text" ? "active" : ""} onClick={() => setInputType("text")}>Paste resume text</button><button type="button" aria-pressed={inputType === "pdf"} className={inputType === "pdf" ? "active" : ""} onClick={() => setInputType("pdf")}>Upload PDF</button></div>
      {inputType === "text" ? <><textarea className="bp-document-text" maxLength={50000} rows={10} placeholder="Paste resume text, including project and experience bullets…" value={resumeText} onChange={(event) => setResumeText(event.target.value)} /><small className="bp-char-count">{charCount(resumeText).toLocaleString()} / 50,000 characters</small></> : <label className="bp-file-drop"><Upload size={18} /><span>{pdf?.name ?? "Choose a text-based PDF (max 5 MB, 25 pages)"}</span><input type="file" accept="application/pdf,.pdf" onChange={(event) => setPdf(event.target.files?.[0])} /></label>}
      <div className="bp-disclosure"><LockKeyhole size={14} /><span>By submitting, your resume text and scanned public-repo evidence are sent to BharatCode first, with Gemini as fallback. BuildProof does not persist the document; extracted excerpts and results stay temporarily in service memory for retrieval.</span></div>
      <button className="analyze-button bp-submit" disabled={busy || !repoUrl.trim() || (inputType === "text" ? !resumeText.trim() : !pdf)} onClick={() => void run()}>{busy ? <><LoaderCircle size={15} className="spin" /> Analyzing claims</> : <>Check resume claims <ChevronDown size={15} /></>}</button>
      <DocumentProgress busy={busy} stage={stage} error={error} onRetry={() => void run()} />
    </section>
    {result && <ResumeResult result={result} id="resume-result" />}
  </main>;
}

function ResumeResult({ result, id }: { result: ResumeAudit; id: string }) {
  const markdown = [`# BuildProof Resume Proof`, ``, `Resume: ${result.resume_name}`, `Repository: ${result.repository.full_name} @ ${result.repository.commit_sha}`, `Model: ${result.model_provider}`, ``, result.summary, ``, ...result.claims.flatMap((claim, index) => [`## Claim ${index + 1}: ${claim.claim}`, `Status: ${claim.status}`, claim.rationale, claim.defensible_rewrite ? `Defensible wording: ${claim.defensible_rewrite}` : "No stronger wording suggested from scanned evidence.", `Resume evidence: ${claim.resume_evidence_ids.join(", ")}`, `Repository evidence: ${claim.repo_evidence_ids.join(", ")}`, ``]), `## Evidence`, ...result.evidence.map((e) => `- ${e.id} ${sourceLabel(e)} — ${e.excerpt}`)].join("\n");
  const labels = { supported: "Supported by scanned code", partly_supported: "Partly supported", not_found_in_scanned_scope: "Not found in scanned scope" };
  return <section className="bp-results" id={id}><div className="bp-result-heading"><div><span className="section-kicker">RESUME PROOF REPORT</span><h2>{result.repository.full_name}</h2><p>{result.summary}</p></div><ReportActions name="buildproof-resume-proof.md" markdown={markdown} /></div><ProviderNote provider={result.model_provider} />
    <div className="bp-claims">{result.claims.map((claim, index) => <article className="bp-claim" key={`${claim.claim}-${index}`}><div className="bp-claim-head"><span className={`bp-status status-${claim.status}`}>{labels[claim.status]}</span><span>Claim {String(index + 1).padStart(2, "0")}</span></div><h3>{claim.claim}</h3><p>{claim.rationale}</p>{claim.defensible_rewrite && <div className="bp-rewrite"><b>More defensible wording</b><p>{claim.defensible_rewrite}</p></div>}<div className="bp-ref-columns"><div><small>RESUME SOURCE</small><EvidenceLinks ids={claim.resume_evidence_ids} evidence={result.evidence} /></div><div><small>REPOSITORY SUPPORT</small><EvidenceLinks ids={claim.repo_evidence_ids} evidence={result.evidence} /></div></div></article>)}</div>
    <EvidencePanel evidence={result.evidence} />
  </section>;
}

type NoticeInput = { name: string; text: string };
const emptyNotice = (): NoticeInput => ({ name: "", text: "" });

export function NoticesMode() {
  const [textNotices, setTextNotices] = useState<NoticeInput[]>([emptyNotice()]);
  const [pdfs, setPdfs] = useState<File[]>([]);
  const [result, setResult] = useState<NoticeReport | null>(null);
  const [busy, setBusy] = useState(false);
  const [stage, setStage] = useState("");
  const [error, setError] = useState("");

  const run = async () => {
    const notices = textNotices.filter((notice) => notice.text.trim());
    if (!notices.length && !pdfs.length) { setError("Paste a notice or add a PDF first."); return; }
    if (notices.length + pdfs.length > 5) { setError("Compare no more than five notices at a time."); return; }
    setError(""); setResult(null); setBusy(true); setStage("Starting notice analysis");
    try {
      const started = await api.notices(notices, pdfs);
      const completed = await pollJob(started.poll_url, setStage);
      setResult(completed.result as NoticeReport);
      window.setTimeout(() => document.getElementById("notice-result")?.scrollIntoView({ behavior: "smooth", block: "start" }), 80);
    } catch (err) { setError(err instanceof Error ? err.message : "Notice analysis failed."); }
    finally { setBusy(false); }
  };

  const demo = () => {
    setPdfs([]); setTextNotices([
      { name: "Original placement notice", text: "Campus Placement Drive — Software Intern\nEligibility: B.Tech students with CGPA 7.0 or higher.\nApplication deadline: 2026-11-10.\nSubmit your resume and transcript through the placement portal." },
      { name: "Updated placement notice", text: "Updated Campus Placement Drive — Software Intern\nEligibility: B.Tech students with CGPA 7.5 or higher.\nApplication deadline: 2026-11-12.\nSubmit your resume and transcript through the placement portal." },
    ]); setResult(null); setError("");
  };

  return <main className="bp-mode-page"><section className="bp-mode-hero"><div className="eyebrow"><span className="eyebrow-line" />CAMPUS NOTICES · CHANGES WITH RECEIPTS</div><h1>Catch what<br /><em>changed.</em></h1><p>Paste notices or upload text-based PDFs. BuildProof extracts requirements and deadlines, compares versions in the order you provide, and links each result to its source.</p><div className="bp-mode-tags"><span><CheckCircle2 size={13} /> Manual comparison</span><span><CalendarDays size={13} /> Calendar export</span></div></section>
    <section className="bp-form-card"><div className="bp-card-title"><span>01</span><div><h2>Add notices, oldest to newest</h2><p>One notice extracts actions; multiple notices show changes and conflicts.</p></div><button type="button" className="bp-example-button" onClick={demo}>Load example</button></div>
      <div className="bp-notice-editor-list">{textNotices.map((notice, index) => <article className="bp-notice-editor" key={index}><div className="bp-notice-editor-head"><label htmlFor={`notice-name-${index}`}>NOTICE {String(index + 1).padStart(2, "0")}</label>{textNotices.length > 1 && <button type="button" onClick={() => setTextNotices((old) => old.filter((_, i) => i !== index))}>Remove</button>}</div><input id={`notice-name-${index}`} className="bp-text-input" placeholder="Optional notice name or version" value={notice.name} onChange={(event) => setTextNotices((old) => old.map((item, i) => i === index ? { ...item, name: event.target.value } : item))} /><textarea className="bp-document-text" rows={5} maxLength={50000} placeholder="Paste the full notice text…" value={notice.text} onChange={(event) => setTextNotices((old) => old.map((item, i) => i === index ? { ...item, text: event.target.value } : item))} /><small className="bp-char-count">{charCount(notice.text).toLocaleString()} / 50,000 characters</small></article>)}</div>
      {textNotices.length < 5 && <button type="button" className="bp-add-notice" onClick={() => setTextNotices((old) => [...old, emptyNotice()])}>+ Add another pasted notice</button>}
      <label className="bp-file-drop bp-notice-upload"><Upload size={18} /><span>{pdfs.length ? `${pdfs.length} PDF${pdfs.length === 1 ? "" : "s"} selected` : "Add text-based PDF notices (max 5 MB and 25 pages each)"}<small>PDFs are compared after pasted notices, in the order selected.</small></span><input type="file" accept="application/pdf,.pdf" multiple onChange={(event) => setPdfs(Array.from(event.target.files ?? []))} /></label>
      <div className="bp-disclosure"><LockKeyhole size={14} /><span>By submitting, notice text and extracted PDF lines are sent to BharatCode first, with Gemini as fallback. BuildProof does not persist the documents; extracted excerpts and results stay temporarily in service memory for retrieval.</span></div>
      <button className="analyze-button bp-submit" disabled={busy || (!textNotices.some((n) => n.text.trim()) && !pdfs.length)} onClick={() => void run()}>{busy ? <><LoaderCircle size={15} className="spin" /> Comparing notices</> : <>Extract and compare <ChevronDown size={15} /></>}</button>
      <DocumentProgress busy={busy} stage={stage} error={error} onRetry={() => void run()} />
    </section>
    {result && <NoticeResult result={result} id="notice-result" />}
  </main>;
}

function NoticeResult({ result, id }: { result: NoticeReport; id: string }) {
  const markdown = [`# BuildProof Campus Notice Report`, ``, result.summary, ``, `Sources: ${result.source_documents.map((doc) => doc.name).join(", ")}`, ``, `## Key facts`, ...result.notice_facts.map((fact) => `- **${fact.notice_name} · ${fact.topic}:** ${fact.value} (${fact.evidence_ids.join(", ")})`), ``, `## Changes`, ...(result.changes.length ? result.changes.map((change) => `- **${change.topic} (${change.status}):** ${change.earlier_value || "—"} → ${change.later_value || "—"} (${change.evidence_ids.join(", ")})`) : ["No version changes found."]), ``, `## Conflicts`, ...(result.conflicts.length ? result.conflicts.map((item) => `- **${item.topic}:** ${item.details} (${item.evidence_ids.join(", ")})`) : ["No conflicts found."]), ``, `## Actions`, ...result.actions.map((action) => `- ${action.action}${action.due_date ? ` · due ${action.due_date}` : ""} (${action.evidence_ids.join(", ")})`)].join("\n");
  const calendarActions = result.actions.filter((action) => /^\d{4}-\d{2}-\d{2}$/.test(action.due_date));
  return <section className="bp-results" id={id}><div className="bp-result-heading"><div><span className="section-kicker">CAMPUS NOTICE REPORT</span><h2>Notice changes and actions</h2><p>{result.summary}</p></div><ReportActions name="buildproof-campus-notices.md" markdown={markdown} onCalendar={calendarActions.length ? () => downloadCalendar(calendarActions) : undefined} /></div><ProviderNote provider={result.model_provider} />
    {result.changes.length > 0 && <section className="bp-result-card"><div className="card-eyebrow"><span>01</span> WHAT CHANGED</div>{result.changes.map((change, i) => <article className="bp-change-row" key={`${change.topic}-${i}`}><span className={`bp-change-status change-${change.status}`}>{change.status}</span><div><h3>{change.topic}</h3><p><del>{change.earlier_value || "Not specified"}</del><b>→</b>{change.later_value || "Removed"}</p><EvidenceLinks ids={change.evidence_ids} evidence={result.evidence} /></div></article>)}</section>}
    {result.conflicts.length > 0 && <section className="bp-result-card bp-conflict-card"><div className="card-eyebrow"><span>!</span> CONFLICTS TO CHECK</div>{result.conflicts.map((conflict, i) => <article className="bp-action-row" key={i}><AlertTriangle size={16} /><div><h3>{conflict.topic}</h3><p>{conflict.details}</p><EvidenceLinks ids={conflict.evidence_ids} evidence={result.evidence} /></div></article>)}</section>}
    <section className="bp-result-card"><div className="card-eyebrow"><span>02</span> KEY FACTS</div><div className="bp-fact-grid">{result.notice_facts.map((fact, i) => <article key={`${fact.topic}-${i}`}><small>{fact.notice_name} · {fact.topic}</small><p>{fact.value}</p><EvidenceLinks ids={fact.evidence_ids} evidence={result.evidence} /></article>)}</div></section>
    <section className="bp-result-card"><div className="card-eyebrow"><span>03</span> ACTION CHECKLIST</div>{result.actions.length ? result.actions.map((action, i) => <article className="bp-action-row" key={`${action.action}-${i}`}><CheckCircle2 size={16} /><div><h3>{action.action}</h3>{action.due_date && <small>Due {action.due_date}</small>}<EvidenceLinks ids={action.evidence_ids} evidence={result.evidence} /></div></article>) : <p className="bp-empty">No concrete actions were extracted from these notices.</p>}{calendarActions.length > 0 && <p className="bp-calendar-note">Download {calendarActions.length} dated action{calendarActions.length === 1 ? "" : "s"} as an .ics calendar file.</p>}</section>
    <EvidencePanel evidence={result.evidence} />
  </section>;
}

function downloadCalendar(actions: NoticeAction[]) {
  downloadFile("buildproof-campus-actions.ics", buildCalendarIcs(actions), "text/calendar;charset=utf-8");
}

function downloadFile(filename: string, content: string, contentType: string) {
  const url = URL.createObjectURL(new Blob([content], { type: contentType }));
  const anchor = document.createElement("a"); anchor.href = url; anchor.download = filename; anchor.click();
  window.setTimeout(() => URL.revokeObjectURL(url), 1000);
}
