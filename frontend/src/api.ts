export interface Evidence {
  id: string;
  path: string;
  source_type?: string;
  source_name?: string;
  page_number?: number | null;
  page_count?: number | null;
  line_start: number;
  line_end: number;
  line_count?: number;
  excerpt: string;
  kind: string;
  extractor: string;
}

export interface JudgeQuestion {
  category: string;
  question: string;
  why: string;
  evidence_ids: string[];
  answer_outline: string[];
  follow_up: string;
}

export interface Report {
  mode: "repo";
  is_sample: boolean;
  model_provider?: "bharatcode" | "gemini" | "sample";
  repository: { full_name: string; url: string; commit_sha: string; default_branch?: string; description?: string | null };
  overview: string;
  purpose: { summary: string; confidence: "low" | "medium" | "high"; is_inference: boolean; evidence_ids: string[] };
  architecture_flow: { step: string; detail: string; evidence_ids: string[] }[];
  judge_questions: JudgeQuestion[];
  claim_checks: { category: string; claim: string; status: string; documentation_evidence_ids: string[]; code_evidence_ids: string[]; coverage_note: string }[];
  findings: { marker: string; path: string; evidence_ids: string[] }[];
  documentation_and_compliance: { readme_present: boolean; setup_instructions_present: boolean; bharatcode_file_present: boolean; env_example_present: boolean; license_file_present?: boolean; template_markers: unknown[] };
  coverage: { files_discovered: number; files_scanned: number; files_skipped: { path: string; reason: string; size_bytes: number }[]; languages_detected: string[]; coverage_notes: string[] };
  evidence: Evidence[];
  secret_findings: { path: string; line: number; kind: string; redacted_excerpt: string; evidence_ids: string[] }[];
  fact_sheet_summary: { stack: { name: string; version?: string | null; scope: string; evidence_ids: string[] }[]; entry_points: { path: string; kind: string; evidence_ids: string[] }[]; routes: { method: string; path: string; framework: string; evidence_ids: string[] }[]; environment_variables: { name: string; required_signal: string; evidence_ids: string[] }[]; integrations: { name: string; evidence_ids: string[] }[] };
}

export interface ResumeClaim {
  claim: string;
  resume_evidence_ids: string[];
  status: "supported" | "partly_supported" | "not_found_in_scanned_scope";
  repo_evidence_ids: string[];
  rationale: string;
  defensible_rewrite: string;
}

export interface ResumeAudit {
  mode: "resume";
  model_provider: "bharatcode" | "gemini";
  summary: string;
  resume_name: string;
  repository: Report["repository"];
  claims: ResumeClaim[];
  evidence: Evidence[];
  coverage: Report["coverage"];
}

export interface NoticeFact {
  notice_name: string;
  topic: string;
  value: string;
  evidence_ids: string[];
}

export interface NoticeChange {
  topic: string;
  earlier_value: string;
  later_value: string;
  status: "changed" | "added" | "removed" | "conflict";
  evidence_ids: string[];
}

export interface NoticeAction {
  action: string;
  due_date: string;
  evidence_ids: string[];
}

export interface NoticeReport {
  mode: "notices";
  model_provider: "bharatcode" | "gemini";
  summary: string;
  source_documents: { name: string }[];
  notice_facts: NoticeFact[];
  changes: NoticeChange[];
  conflicts: { topic: string; details: string; evidence_ids: string[] }[];
  actions: NoticeAction[];
  evidence: Evidence[];
}

export interface JobResponse {
  job_id: string;
  poll_url: string;
  cache_hit: boolean;
}

export interface JobStatus {
  job_id: string;
  poll_url?: string;
  status: "queued" | "running" | "completed" | "failed";
  stage: string;
  cache_hit: boolean;
  result?: Report | ResumeAudit | NoticeReport | PracticeFeedback;
  error?: string;
}

export interface PracticeFeedback {
  covered: string[];
  add_next: string[];
  example_answer: string;
  evidence_ids: string[];
  is_sample?: boolean;
  model_provider?: "bharatcode" | "gemini" | "sample";
}

const BASE = (import.meta.env.VITE_API_BASE_URL as string | undefined)?.replace(/\/$/, "") ?? "";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    const headers = new Headers(init?.headers);
    if (!(init?.body instanceof FormData) && !headers.has("content-type")) headers.set("content-type", "application/json");
    res = await fetch(`${BASE}/api${path}`, { ...init, headers });
  } catch {
    throw new Error("Can't reach the analysis service. It may be starting up; try again in a few seconds.");
  }
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(typeof body.detail === "string" ? body.detail : `The service returned ${res.status}.`);
  }
  return res.json() as Promise<T>;
}

export const api = {
  start: (repo_url: string) => request<JobResponse>("/analyze", { method: "POST", body: JSON.stringify({ repo_url }) }),
  poll: (url: string) => request<JobStatus>(url.replace(/^\/api/, "")),
  sample: () => request<Report>("/sample"),
  practice: (report: Report, question_index: number, answer: string) =>
    request<JobResponse>("/practice", { method: "POST", body: JSON.stringify({ full_name: report.repository.full_name, commit_sha: report.repository.commit_sha, question_index, is_sample: report.is_sample, answer }) }),
  resumeAudit: (repo_url: string, resume_text: string, resume_pdf?: File) => {
    const body = new FormData(); body.set("repo_url", repo_url);
    if (resume_pdf) body.set("resume_pdf", resume_pdf); else body.set("resume_text", resume_text);
    return request<JobResponse>("/resume-audit", { method: "POST", body });
  },
  notices: (notice_texts: { name: string; text: string }[], notice_pdfs: File[]) => {
    const body = new FormData();
    if (notice_texts.length) body.set("notice_texts", JSON.stringify(notice_texts));
    notice_pdfs.forEach((file) => body.append("notice_pdfs", file));
    return request<JobResponse>("/notices/analyze", { method: "POST", body });
  },
};
