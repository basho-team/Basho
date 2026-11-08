/** Tipos das respostas da API do Basho (espelham os modelos Pydantic do backend). */
export type ClaimSection = "technological_challenge" | "hypothesis" | "method" | "result" | "uncertainty";
export type ClaimStatus = "supported" | "pending" | "disputed";
export type Outcome = "positive" | "negative" | "inconclusive";
export type ReviewState = "text_approved" | "changes_requested" | "awaiting_review";

export interface Period {
  start: string;
  end: string;
  timezone: string;
  periodicity: string;
}

export interface Person {
  id: string;
  name: string;
  role: "researcher" | "manager" | "fiscal";
}

export interface DemoContext {
  is_synthetic: boolean;
  project_id: string;
  project_name: string;
  period: Period;
  fiscal_year: number;
  people: Person[];
  ai_maker_available: boolean;
  ai_checker_available: boolean;
  ai_detail: string;
}

export interface EvidenceEvent {
  id: string;
  project_id: string;
  kind: string;
  source: string;
  source_ref: string | null;
  actor: { type: string; id: string; model?: string | null };
  payload: Record<string, unknown>;
  supersedes: string | null;
  is_synthetic: boolean;
  content_hash: string;
  created_at: string;
}

export interface ReportClaim {
  section: ClaimSection;
  text: string;
  status: ClaimStatus;
  evidence_ids: string[];
  question?: string | null;
  ask_role?: string | null;
  dispute_reason?: string | null;
}

export interface Experiment {
  description: string;
  outcome: Outcome;
  evidence_ids: string[];
}

export interface Missing {
  field: string;
  question: string;
  ask_role: string;
}

export interface Draft {
  project_id: string;
  researcher_id: string;
  period: Period;
  summary: string;
  claims: ReportClaim[];
  experiments: Experiment[];
  missing: Missing[];
  formal_hours_event_ids: string[];
  eligibility_note?: string;
}

export interface ChangeRecord {
  author_id: string;
  author_role: string;
  reason: string;
  operations: string[];
  affected_claim_ids: string[];
  added_claim_ids: string[];
  withdrawn: { claim_id: string; reason: string }[];
  resolved_gaps: { missing_id: string; field: string; evidence_ids: string[]; formal_hours_event_ids: string[] }[];
}

export interface ReportVersion {
  id: string;
  number: number;
  draft: Draft;
  claim_ids: string[];
  experiment_ids: string[];
  missing_ids: string[];
  supersedes_id: string | null;
  change: ChangeRecord | null;
  created_at: string;
  is_synthetic: boolean;
}

export interface RoleReview {
  state: ReviewState;
  review_id: string | null;
}

export interface ReportStatus {
  researcher_id: string;
  current_version_id: string;
  current_version_number: number;
  researcher: RoleReview;
  manager: RoleReview;
  approved_version_number: number | null;
  approval_outdated: boolean;
  formal_hours_event_ids: string[];
}

export interface ReportVersionOut {
  version: ReportVersion;
  status: ReportStatus;
  is_current: boolean;
  current_version_id: string;
  content_hash: string;
  evidence_event_id: string;
}

export interface CheckIssue {
  code: string;
  message: string;
  severity: string;
  evidence_id: string | null;
}

export interface ChecksOut {
  deterministic: { verdict: "pass" | "fail"; issues: CheckIssue[]; checker: string };
  checker_status: "unavailable";
  checker_detail: string;
}

export interface SourceRef {
  researcher_id: string;
  version_id: string;
  version_number: number;
  item_kind: "claim" | "experiment" | "missing";
  item_id: string;
  researcher_review_id: string | null;
}

export interface ConsolidatedItem {
  text?: string;
  description?: string;
  section?: ClaimSection;
  outcome?: Outcome;
  evidence_ids: string[];
  source: SourceRef;
}

export interface Consolidation {
  consolidation_id: string;
  reports: ReportStatus[];
  advances: ConsolidatedItem[];
  results: ConsolidatedItem[];
  result_claims: ConsolidatedItem[];
  uncertainties: ConsolidatedItem[];
  open_questions: { question: string; ask_role: string; topic: string; text: string | null; evidence_ids: string[]; source: SourceRef }[];
  disputes: { text: string; reason: string; evidence_ids: string[]; source: SourceRef }[];
  outcome_counts: Record<Outcome, number>;
  all_text_approved: boolean;
  is_synthetic: boolean;
  note: string;
}

export interface ConsolidationOut {
  consolidation: Consolidation | null;
  summary_markdown: string | null;
}

export interface FiscalSource {
  reference: string;
  revision: string;
  locator: string;
  origin: string;
}

export interface DossierItem {
  researcher_id: string;
  version_id: string;
  item_kind: "claim" | "experiment" | "missing";
  item_id: string;
  status: string;
  text: string;
  sources: FiscalSource[];
  gaps: string[];
  researcher_review_id: string | null;
}

export interface Dossier {
  consolidation_id: string;
  period_start: string;
  period_end: string;
  period_gaps: string[];
  researchers: {
    researcher_id: string;
    version_id: string;
    version_number: number;
    researcher_review_id: string | null;
    formal_hours: FiscalSource[];
    gaps: string[];
  }[];
  items: DossierItem[];
  note: string;
}

export interface VersionConflict {
  detail: string;
  requested_version_id: string;
  current_version_id: string;
}
