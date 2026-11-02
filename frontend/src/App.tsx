import { useRef, useState } from "react";
import { ArrowDown, ArrowUpRight, BookOpen, Check, ChevronRight, CircleAlert, Clipboard, Download, ExternalLink, FileCode2, Github, LoaderCircle, LockKeyhole, Play, Printer, RefreshCw, ShieldCheck, Sparkles, TerminalSquare } from "lucide-react";
import { api, type Evidence, type JudgeQuestion, type JobStatus, type PracticeFeedback, type Report } from "./api";
import { NoticesMode, ResumeMode, type BuildMode } from "./DocumentModes";

const STAGES: Record<string, string> = { queued: "In the queue", resolving_repository: "Finding the latest commit", fetching_archive: "Fetching the public source", scanning_files: "Reading the project structure", building_grounded_report: "Preparing your judge briefing", reviewing_answer: "Reviewing your answer", joining_existing_analysis: "Joining an analysis already in progress", complete: "Ready" };
const sleep = (ms: number) => new Promise((resolve) => window.setTimeout(resolve, ms));

async function pollJob(pollUrl: string, onUpdate: (job: JobStatus) => void): Promise<JobStatus> {
  const started = Date.now();
  while (Date.now() - started < 4 * 60 * 1000) {
    const job = await api.poll(pollUrl); onUpdate(job);
    if (job.status === "completed") return job;
    if (job.status === "failed") throw new Error(job.error ?? "This job failed. Try again.");
    await sleep(1500);
  }
  throw new Error("This is taking longer than expected. The analysis may still be running; submit the repo again to check the cached result.");
}

function evidenceLabel(e: Evidence) {
  const source = e.source_name ?? e.path;
  const location = e.page_number ? `p.${e.page_number} · ` : "";
  return `${source} · ${location}${e.line_start}${e.line_end > e.line_start ? `–${e.line_end}` : ""}`;
}
function EvidenceRefs({ ids, evidence }: { ids: string[]; evidence: Evidence[] }) {
  const items = ids.map((id) => evidence.find((item) => item.id === id)).filter((item): item is Evidence => Boolean(item));
  if (!items.length) return <span className="no-evidence">No source lines were captured for this item.</span>;
  return <div className="evidence-refs">{items.map((item) => <a href={`#evidence-${item.id}`} key={item.id} title={item.excerpt}><FileCode2 size={13} />{evidenceLabel(item)}</a>)}</div>;
}
function StageLabel({ stage }: { stage: string }) { return <>{STAGES[stage] ?? stage.replaceAll("_", " ")}</>; }

export function App() {
  const [mode, setMode] = useState<BuildMode>("repo");
  const [repoUrl, setRepoUrl] = useState("");
  const [report, setReport] = useState<Report | null>(null);
  const [job, setJob] = useState<JobStatus | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [purposeEdit, setPurposeEdit] = useState(false);
  const requestVersion = useRef(0);
  const resultsRef = useRef<HTMLElement>(null);

  const startAnalysis = async (url = repoUrl) => {
    const version = ++requestVersion.current;
    setBusy(true); setError(""); setReport(null); setJob(null); setPurposeEdit(false);
    try {
      const created = await api.start(url.trim());
      setJob({ job_id: created.job_id, poll_url: created.poll_url, cache_hit: created.cache_hit, status: "queued", stage: created.cache_hit ? "complete" : "queued" });
      const completed = await pollJob(created.poll_url, (next) => { if (version === requestVersion.current) setJob({ ...next, poll_url: created.poll_url }); });
      if (version !== requestVersion.current) return;
      setReport(completed.result as Report); setJob({ ...completed, poll_url: created.poll_url });
      window.setTimeout(() => resultsRef.current?.scrollIntoView({ behavior: "smooth", block: "start" }), 80);
    } catch (err) {
      if (version === requestVersion.current) setError(err instanceof Error ? err.message : "Something went wrong.");
    } finally { if (version === requestVersion.current) setBusy(false); }
  };

  const openSample = async () => {
    requestVersion.current++; setBusy(true); setError(""); setJob(null);
    try {
      const sample = await api.sample(); setReport(sample); setRepoUrl("");
      window.setTimeout(() => resultsRef.current?.scrollIntoView({ behavior: "smooth", block: "start" }), 80);
    } catch (err) { setError(err instanceof Error ? err.message : "The sample could not be loaded."); }
    finally { setBusy(false); }
  };

  const exportMarkdown = () => {
    if (!report) return;
    const blob = new Blob([toMarkdown(report)], { type: "text/markdown;charset=utf-8" });
    const url = URL.createObjectURL(blob); const anchor = document.createElement("a");
    anchor.href = url; anchor.download = `${report.repository.full_name.replaceAll("/", "-")}-repo-brief.md`;
    anchor.click(); window.setTimeout(() => URL.revokeObjectURL(url), 1000);
  };

  return <div className="app-shell">
    <header className="topbar"><a className="brand" href="#top" aria-label="BuildProof home"><span className="brand-mark"><ShieldCheck size={18} /></span><span>build<span className="brand-light">proof</span></span></a><div className="topbar-right"><span className="topbar-note"><span className="live-dot" />Evidence for your next move</span><a href="#modes" className="github-link">Choose a mode <ArrowUpRight size={13} /></a></div></header>
    <nav className="mode-nav" id="modes" aria-label="BuildProof modes">
      <button className={mode === "repo" ? "active" : ""} onClick={() => setMode("repo")}><span>01</span> Defend a repo</button>
      <button className={mode === "resume" ? "active" : ""} onClick={() => setMode("resume")}><span>02</span> Prove resume claims</button>
      <button className={mode === "notices" ? "active" : ""} onClick={() => setMode("notices")}><span>03</span> Track campus notices</button>
    </nav>
    {mode === "repo" && <main id="top">
      <section className="hero" aria-labelledby="hero-title"><div className="hero-grain" /><div className="hero-copy">
        <div className="eyebrow"><span className="eyebrow-line" />HACKATHON PREP, WITH RECEIPTS</div>
        <h1 id="hero-title">Know your repo.<br /><em>Defend your decisions.</em></h1>
        <p className="hero-lede">A judge can ask anything. Get a clear architecture walkthrough, practice the hard questions, and take every answer back to the exact lines of code.</p>
        <form className="repo-form" onSubmit={(event) => { event.preventDefault(); void startAnalysis(); }}>
          <label htmlFor="repo-url">PUBLIC GITHUB REPOSITORY</label><div className="repo-input-wrap"><Github size={17} /><input id="repo-url" type="url" placeholder="https://github.com/owner/repository" value={repoUrl} onChange={(event) => setRepoUrl(event.target.value)} disabled={busy} required /><button className="analyze-button" type="submit" disabled={busy || !repoUrl.trim()}>{busy ? <LoaderCircle size={16} className="spin" /> : <><span>Analyze repo</span><ArrowUpRight size={16} /></>}</button></div>
          <div className="form-under"><span><LockKeyhole size={13} /> Public repos only · source is never executed</span><button type="button" onClick={() => void openSample()} disabled={busy}><Play size={12} fill="currentColor" /> Try the sample demo</button></div>
        </form>
        {busy && <div className="job-progress" role="status"><LoaderCircle size={17} className="spin" /><span><strong><StageLabel stage={job?.stage ?? "resolving_repository"} /></strong><small>{job?.cache_hit ? "Using a verified cached briefing" : "Usually 30–90 seconds. Keep this page open."}</small></span><span className="progress-pips"><i /><i /><i /></span></div>}
        {error && <div className="error-banner" role="alert"><CircleAlert size={16} /><span>{error}</span><button onClick={() => void startAnalysis()} disabled={!repoUrl.trim() || busy}><RefreshCw size={14} /> Retry</button></div>}
        <div className="hero-proof"><div className="proof-icon"><FileCode2 size={17} /></div><div><strong>Evidence, not guesswork.</strong><span>Every generated question links to source lines your judges can inspect.</span></div></div>
      </div><div className="hero-art" aria-hidden="true"><div className="art-orbit orbit-one" /><div className="art-orbit orbit-two" /><div className="orbit-label label-top">STATIC ANALYSIS <span>01—04</span></div><div className="code-card"><div className="code-card-head"><div className="window-dots"><i /><i /><i /></div><span>src/api/routes.py</span><span className="code-state">READ ONLY</span></div><div className="code-lines"><div><b>01</b><span className="code-purple">@app.get</span><span className="code-green">("/health")</span></div><div><b>02</b><span className="code-muted">def </span><span className="code-blue">health_check</span><span>():</span></div><div><b>03</b><span className="code-muted indent">return </span><span className="code-green">{"{"}"status": "ok"{"}"}</span></div><div className="code-highlight"><b>04</b><span className="code-comment"># Evidence E001 · route</span></div></div><div className="evidence-chip"><span className="check-mini"><Check size={11} /></span><span><b>E001</b> citation verified</span><ArrowUpRight size={13} /></div></div><div className="floating-tag tag-top"><Sparkles size={14} /><span>5 judge questions</span></div><div className="floating-tag tag-bottom"><span className="tag-bars"><i /><i /><i /></span><span>3-round practice</span></div><div className="orbit-label label-bottom">YOUR REPO · YOUR STORY <span>EST. 2026</span></div></div></section>

      {!report && <section className="how-section" id="how-it-works"><div className="section-kicker">A BETTER KIND OF REHEARSAL</div><div className="how-grid"><article><span className="step-no">01</span><BookOpen size={21} /><h3>See the shape</h3><p>Get a readable overview of your stack, entry points, routes, and how the pieces fit together.</p></article><article><span className="step-no">02</span><FileCode2 size={21} /><h3>Follow the evidence</h3><p>Questions and claims link to exact file and line references. No source is run.</p></article><article><span className="step-no">03</span><TerminalSquare size={21} /><h3>Practice out loud</h3><p>Answer three judge-style questions. Get concrete feedback against the answer outline.</p></article></div><div className="privacy-strip"><span><LockKeyhole size={15} /> Public source only</span><span><Check size={15} /> No code execution</span><span><Check size={15} /> No hosted report pages</span></div></section>}
      {report && <section className="report-section" ref={resultsRef}><ReportView report={report} onExport={exportMarkdown} purposeEdit={purposeEdit} setPurposeEdit={setPurposeEdit} setReport={setReport} /></section>}
    </main>}
    {mode === "resume" && <ResumeMode />}
    {mode === "notices" && <NoticesMode />}
    <footer className="footer"><a className="brand brand-footer" href="#top"><span className="brand-mark"><ShieldCheck size={15} /></span><span>build<span className="brand-light">proof</span></span></a><span>Every claim has a source. Every next step is yours.</span><a href="https://bharatcode.ai/hackathon" target="_blank" rel="noreferrer">BharatCode Build League <ExternalLink size={13} /></a></footer>
  </div>;
}

function ReportView({ report, onExport, purposeEdit, setPurposeEdit, setReport }: { report: Report; onExport: () => void; purposeEdit: boolean; setPurposeEdit: (open: boolean) => void; setReport: (update: (old: Report | null) => Report | null) => void }) {
  const [activePractice, setActivePractice] = useState<number | null>(null);
  const [answers, setAnswers] = useState<Record<number, string>>({});
  const [feedback, setFeedback] = useState<Record<number, PracticeFeedback>>({});
  const [practiceBusy, setPracticeBusy] = useState<number | null>(null);
  const [practiceError, setPracticeError] = useState("");
  const [practiceStage, setPracticeStage] = useState("");
  const [copied, setCopied] = useState(false);

  const runPractice = async (index: number) => {
    const question = report.judge_questions[index]; const answer = answers[index]?.trim();
    if (!question || !answer) return;
    setPracticeBusy(index); setPracticeError(""); setPracticeStage("Starting your practice review");
    try {
      const job = await api.practice(report, index, answer);
      const result = await pollJob(job.poll_url, (state) => setPracticeStage(STAGES[state.stage] ?? "Reviewing your answer"));
      setFeedback((old) => ({ ...old, [index]: result.result as PracticeFeedback }));
    } catch (err) { setPracticeError(err instanceof Error ? err.message : "Practice feedback is unavailable."); }
    finally { setPracticeBusy(null); }
  };
  const copyBrief = async () => { await navigator.clipboard.writeText(toMarkdown(report)); setCopied(true); window.setTimeout(() => setCopied(false), 1800); };

  return <>
    <div className="report-topline"><div><span className="section-kicker">YOUR REPO BRIEFING</span><h2>{report.repository.full_name}</h2><a className="repo-source" href={report.repository.url} target="_blank" rel="noreferrer"><Github size={14} /> Open source repo <ArrowUpRight size={13} /></a></div><div className="report-actions"><button className="secondary-button" onClick={() => void copyBrief()}><Clipboard size={15} />{copied ? "Copied" : "Copy brief"}</button><button className="secondary-button" onClick={onExport}><Download size={15} />Export Markdown</button><button className="secondary-button" onClick={() => window.print()}><Printer size={15} />Print</button></div></div>
    {report.is_sample && <div className="sample-banner"><Sparkles size={16} /><span><strong>Sample demo</strong> — This is an illustrative report, not a live repository analysis.</span></div>}
    <div className="report-meta"><span><i className="meta-dot" />{report.repository.default_branch ?? "Pinned commit"} · {report.repository.commit_sha.slice(0, 8)}</span><span>{report.coverage.files_scanned} files scanned</span><span>{report.coverage.languages_detected.join(" · ") || "Language not identified"}</span><span>{report.coverage.files_skipped.length} skipped</span><span>Model: {modelLabel(report.model_provider)}</span></div>

    <div className="report-layout"><div className="report-main-column">
      <article className="report-card overview-card"><div className="card-eyebrow"><span>01</span> PROJECT OVERVIEW</div><p className="overview-text">{report.overview}</p><div className="purpose-box"><div className="purpose-heading"><span>{report.purpose.is_inference ? "INFERRED PURPOSE" : "PROJECT PURPOSE"}{report.purpose.is_inference && <em>{report.purpose.confidence} confidence</em>}</span><button onClick={() => setPurposeEdit(!purposeEdit)}>{purposeEdit ? "Done" : "Edit"}</button></div>{purposeEdit ? <textarea value={report.purpose.summary} onChange={(e) => setReport((old) => old ? { ...old, purpose: { ...old.purpose, summary: e.target.value } } : old)} rows={2} aria-label="Edit inferred project purpose" /> : <p>{report.purpose.summary}</p>}<EvidenceRefs ids={report.purpose.evidence_ids} evidence={report.evidence} /></div></article>
      <article className="report-card"><div className="card-eyebrow"><span>02</span> HOW THE APP FITS TOGETHER</div><div className="flow-list">{report.architecture_flow.map((step, i) => <div className="flow-step" key={`${step.step}-${i}`}><div className="flow-number">{String(i + 1).padStart(2, "0")}</div><div className="flow-content"><h3>{step.step}</h3><p>{step.detail}</p><EvidenceRefs ids={step.evidence_ids} evidence={report.evidence} /></div>{i < report.architecture_flow.length - 1 && <ChevronRight className="flow-arrow" size={16} />}</div>)}</div></article>
      {report.claim_checks.length > 0 && <article className="report-card"><div className="card-eyebrow"><span>03</span> DOCUMENTED CLAIMS CHECK</div><p className="card-intro">Static signals help compare documentation with scanned code. A missing signal is not proof the feature is absent.</p><div className="claim-list">{report.claim_checks.map((claim, i) => <div className="claim-row" key={`${claim.category}-${i}`}><div className={`claim-status ${claim.status === "evidence_found" ? "claim-ok" : "claim-missing"}`}>{claim.status === "evidence_found" ? <Check size={14} /> : <CircleAlert size={14} />}</div><div><div className="claim-title">{claim.category.replaceAll("_", " ")} <span>{claim.status === "evidence_found" ? "code signal found" : "not found in scanned scope"}</span></div><p>“{claim.claim}”</p><EvidenceRefs ids={[...claim.documentation_evidence_ids, ...claim.code_evidence_ids]} evidence={report.evidence} /><small>{claim.coverage_note}</small></div></div>)}</div></article>}
      <article className="report-card questions-card"><div className="card-eyebrow"><span>04</span> QUESTIONS A JUDGE MAY ASK <b>{report.judge_questions.length} PREPPED</b></div><p className="card-intro">Specific prompts grounded in your scanned files. Use the answer outline as a starting point, not a script.</p><div className="questions-list">{report.judge_questions.map((question, i) => <QuestionCard key={`${question.question}-${i}`} question={question} index={i} evidence={report.evidence} active={activePractice === i} onPractice={() => { setActivePractice(activePractice === i ? null : i); setPracticeError(""); }} />)}</div></article>
    </div><aside className="report-side-column">
      <div className="report-card practice-card"><div className="practice-heading"><span className="practice-icon"><TerminalSquare size={17} /></span><div><div className="card-eyebrow">MOCK JUDGE</div><h3>Say it in your own words.</h3></div></div><p>Answer three questions. Get useful feedback against the outline and source evidence.</p><div className="practice-progress"><span>{Object.keys(feedback).length} of 3 answered</span><div><i style={{ width: `${Math.min(Object.keys(feedback).length, 3) * 33.333}%` }} /></div></div>
        {report.judge_questions.slice(0, 3).map((question, i) => <div className={`practice-question ${activePractice === i ? "is-active" : ""}`} key={`practice-${i}`}><button className="practice-question-head" onClick={() => { setActivePractice(activePractice === i ? null : i); setPracticeError(""); }}><span className="practice-qno">0{i + 1}</span><span>{question.question}</span>{feedback[i] ? <span className="practice-done"><Check size={13} /></span> : <ChevronRight size={15} />}</button>{activePractice === i && <div className="practice-answer"><div className="answer-outline"><b>ANSWER OUTLINE</b><ul>{question.answer_outline.map((item, n) => <li key={n}>{item}</li>)}</ul></div><label htmlFor={`answer-${i}`}>YOUR ANSWER · DON'T INCLUDE CREDENTIALS</label><textarea id={`answer-${i}`} rows={4} maxLength={5000} placeholder="Try explaining it as if a judge just asked…" value={answers[i] ?? ""} onChange={(e) => setAnswers((old) => ({ ...old, [i]: e.target.value }))} /><button className="practice-submit" disabled={!answers[i]?.trim() || practiceBusy === i} onClick={() => void runPractice(i)}>{practiceBusy === i ? <><LoaderCircle size={14} className="spin" /> {practiceStage}</> : <><Play size={13} fill="currentColor" /> Get feedback</>}</button>{practiceError && practiceBusy === null && <p className="practice-error">{practiceError}</p>}{feedback[i] && <Feedback feedback={feedback[i]} evidence={report.evidence} />}</div>}</div>)}
        <div className="practice-note"><LockKeyhole size={13} /> Answers are sent to the selected model provider for feedback; this app does not save them.</div></div>

      <div className="report-card facts-card"><div className="card-eyebrow">STATIC FACT SHEET</div><FactList title="STACK & DEPENDENCIES" items={report.fact_sheet_summary.stack.map((x) => ({ label: x.name, detail: x.version ?? x.scope, ids: x.evidence_ids }))} evidence={report.evidence} empty="No supported dependency manifests found." /><FactList title="ENTRY POINTS" items={report.fact_sheet_summary.entry_points.map((x) => ({ label: x.path, detail: x.kind, ids: x.evidence_ids }))} evidence={report.evidence} empty="No recognized entry point names found." /><FactList title="ROUTES" items={report.fact_sheet_summary.routes.map((x) => ({ label: `${x.method} ${x.path}`, detail: x.framework, ids: x.evidence_ids }))} evidence={report.evidence} empty="No Flask, FastAPI, or Express route patterns found." /><FactList title="ENVIRONMENT VARIABLE NAMES" items={report.fact_sheet_summary.environment_variables.map((x) => ({ label: x.name, detail: x.required_signal, ids: x.evidence_ids }))} evidence={report.evidence} empty="No environment variable reads found." /><FactList title="INTEGRATIONS" items={report.fact_sheet_summary.integrations.map((x) => ({ label: x.name, detail: "static signal", ids: x.evidence_ids }))} evidence={report.evidence} empty="No known integration signals found." /></div>
      <div className="report-card checks-card"><div className="card-eyebrow">DOCS & COMPLIANCE</div><CheckRow label="README" value={report.documentation_and_compliance.readme_present} /><CheckRow label="Setup instructions" value={report.documentation_and_compliance.setup_instructions_present} /><CheckRow label="BharatCode.txt" value={report.documentation_and_compliance.bharatcode_file_present} /><CheckRow label=".env.example" value={report.documentation_and_compliance.env_example_present} /><CheckRow label="License file" value={Boolean(report.documentation_and_compliance.license_file_present)} neutral={!report.documentation_and_compliance.license_file_present} />{report.secret_findings.length > 0 && <div className="secret-warning"><CircleAlert size={14} /><div><b>{report.secret_findings.length} possible secret signal{report.secret_findings.length === 1 ? "" : "s"}</b><span>Values are redacted and never sent to the model.</span>{report.secret_findings.map((item, i) => <code key={i}>{item.path}:{item.line} · {item.kind}</code>)}</div></div>}{report.findings.length > 0 && <div className="template-warning"><b>Template markers</b>{report.findings.map((item, i) => <div key={i}>{item.marker} · {item.path}<EvidenceRefs ids={item.evidence_ids} evidence={report.evidence} /></div>)}</div>}</div>
    </aside></div>
    {report.coverage.coverage_notes.length > 0 && <div className="coverage-notice"><CircleAlert size={16} /><div><strong>Coverage notes</strong>{report.coverage.coverage_notes.map((note, i) => <p key={i}>{note}</p>)}</div></div>}
    <details className="evidence-library"><summary><span><FileCode2 size={17} /> Evidence library</span><span>{report.evidence.length} references <ArrowDown size={14} /></span></summary><div className="evidence-grid">{report.evidence.map((item) => <article className="evidence-item" id={`evidence-${item.id}`} key={item.id}><header><b>{item.id}</b><code>{evidenceLabel(item)}</code><span>{item.kind.replaceAll("_", " ")}</span></header><pre>{item.excerpt}</pre></article>)}</div></details>
    <div className="report-bottom"><span><ShieldCheck size={15} /> Analysis is static and evidence-checked. Verify critical findings yourself.</span><button onClick={() => window.scrollTo({ top: 0, behavior: "smooth" })}>Analyze another repo <ArrowUpRight size={14} /></button></div>
  </>;
}

function QuestionCard({ question, index, evidence, active, onPractice }: { question: JudgeQuestion; index: number; evidence: Evidence[]; active: boolean; onPractice: () => void }) {
  return <article className="judge-question"><div className="judge-qtitle"><span className="judge-qnum">Q{String(index + 1).padStart(2, "0")}</span><span className="category-chip">{question.category.replaceAll("_", " ")}</span><h3>{question.question}</h3><button aria-label={active ? "Close practice" : "Practice this question"} onClick={onPractice}><Play size={13} fill="currentColor" /></button></div><div className="judge-qbody"><p><b>Why it matters</b>{question.why}</p><div className="answer-outline"><b>ANSWER OUTLINE</b><ul>{question.answer_outline.map((item, i) => <li key={i}>{item}</li>)}</ul></div><p className="follow-up"><b>Possible follow-up</b>{question.follow_up}</p><EvidenceRefs ids={question.evidence_ids} evidence={evidence} /></div></article>;
}

function Feedback({ feedback, evidence }: { feedback: PracticeFeedback; evidence: Evidence[] }) {
  return <div className="feedback-box"><div className="feedback-title"><Sparkles size={14} /> {feedback.is_sample ? "SAMPLE PRACTICE FEEDBACK · ILLUSTRATIVE" : `PRACTICE NOTES · ${modelLabel(feedback.model_provider)}`}</div>{feedback.covered.length > 0 && <div><b>You covered</b><ul>{feedback.covered.map((item, i) => <li key={i}>{item}</li>)}</ul></div>}{feedback.add_next.length > 0 && <div><b>To make it stronger</b><ul>{feedback.add_next.map((item, i) => <li key={i}>{item}</li>)}</ul></div>}<div><b>Example answer</b><p>{feedback.example_answer}</p></div><EvidenceRefs ids={feedback.evidence_ids} evidence={evidence} /></div>;
}

function modelLabel(provider?: Report["model_provider"]): string {
  if (provider === "gemini") return "Gemini 3.5 Flash-Lite fallback";
  if (provider === "bharatcode") return "BharatCode Qwen 3.8 27B";
  return provider === "sample" ? "Sample" : "Not reported";
}

function FactList({ title, items, evidence, empty }: { title: string; items: { label: string; detail: string | null; ids: string[] }[]; evidence: Evidence[]; empty: string }) {
  return <section className="fact-group"><h4>{title}<span>{items.length}</span></h4>{items.length ? items.slice(0, 12).map((item, i) => <div className="fact-item" key={`${item.label}-${i}`}><div><code>{item.label}</code><small>{item.detail}</small></div><EvidenceRefs ids={item.ids} evidence={evidence} /></div>) : <p className="fact-empty">{empty}</p>}</section>;
}
function CheckRow({ label, value, neutral = false }: { label: string; value: boolean; neutral?: boolean }) { return <div className="check-row"><span>{label}</span><b className={neutral ? "check-neutral" : value ? "check-yes" : "check-no"}>{neutral ? "Not detected" : value ? "Found" : "Missing"}</b></div>; }

function toMarkdown(report: Report): string {
  const refs = (ids: string[]) => ids.map((id) => { const e = report.evidence.find((item) => item.id === id); return e ? `\`${e.path}:${e.line_start}${e.line_end > e.line_start ? `-${e.line_end}` : ""}\`` : `\`${id} (unverified)\``; }).join(", ");
  const lines = [`# Repo Defense Brief: ${report.repository.full_name}`, "", `> ${report.is_sample ? "SAMPLE — NOT A LIVE REPOSITORY ANALYSIS" : `Commit ${report.repository.commit_sha}`}`, "", "## Overview", report.overview, "", "## Purpose", `${report.purpose.summary}${report.purpose.is_inference ? ` (inferred, ${report.purpose.confidence} confidence)` : ""} — ${refs(report.purpose.evidence_ids)}`, "", "## Architecture flow"];
  for (const step of report.architecture_flow) lines.push(`- **${step.step}:** ${step.detail} ${refs(step.evidence_ids)}`);
  lines.push("", "## Claims checked");
  if (!report.claim_checks.length) lines.push("No matching claims found in scanned docs.");
  for (const claim of report.claim_checks) lines.push(`- **${claim.category} — ${claim.status}:** ${claim.claim} (${refs([...claim.documentation_evidence_ids, ...claim.code_evidence_ids])})`);
  lines.push("", "## Judge questions");
  for (const [i, q] of report.judge_questions.entries()) {
    lines.push(`### ${i + 1}. ${q.question}`, `**Why:** ${q.why}`, "**Answer outline:**", ...q.answer_outline.map((x) => `- ${x}`), `**Follow-up:** ${q.follow_up}`, `**Evidence:** ${refs(q.evidence_ids)}`, "");
  }
  lines.push("## Documentation and compliance", `- README: ${report.documentation_and_compliance.readme_present ? "found" : "missing"}`, `- Setup instructions: ${report.documentation_and_compliance.setup_instructions_present ? "found" : "missing"}`, `- BharatCode.txt: ${report.documentation_and_compliance.bharatcode_file_present ? "found" : "missing"}`, `- .env.example: ${report.documentation_and_compliance.env_example_present ? "found" : "missing"}`, "", "## Scan coverage", `Scanned ${report.coverage.files_scanned} of ${report.coverage.files_discovered} archive entries. Languages: ${report.coverage.languages_detected.join(", ") || "not identified"}.`, ...report.coverage.coverage_notes.map((x) => `- ${x}`), "", "## Evidence excerpts");
  for (const item of report.evidence) lines.push(`- **${item.id} · ${item.path}:${item.line_start}-${item.line_end}** (${item.kind})`, `  \`${item.excerpt.replaceAll("`", "'")}\``);
  lines.push("", "---", "Generated by Repo Defense Coach. Static analysis only; verify critical findings yourself.");
  return lines.join("\n");
}
