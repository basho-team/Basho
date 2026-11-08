/**
 * PROVISÓRIO: aguardando ratificação do Vitor (dono dos contratos do backend).
 *
 * Estes schemas seguem a proposta de CONTRATOS.md (pacote de transferência de 07/11/2026)
 * para que a UI dos três papéis avance antes do backend. Quando o OpenAPI real existir,
 * os tipos passam a vir de `src/lib/api/schema.d.ts` (`npm run gen:api`) e este arquivo
 * vira apenas a validação de runtime — ou é removido. Não crie formatos paralelos fora daqui.
 */
import { z } from "zod";

/** IDs são opacos para a UI. */
const Id = z.string().min(1);
const Timestamp = z.iso.datetime({ offset: true });
/** Valores monetários como string decimal: a UI não faz aritmética fiscal. */
const DecimalString = z.string().regex(/^-?\d+(\.\d+)?$/);

export const RoleSchema = z.enum(["researcher", "manager", "fiscal"]);

export const ApiErrorSchema = z.object({
  code: z.string().min(1),
  message: z.string().min(1),
  correlation_id: z.string().min(1),
  retryable: z.boolean(),
});

export const ProjectSchema = z.object({
  id: Id,
  organization_id: Id,
  organization_name: z.string().min(1),
  name: z.string().min(1),
  objective: z.string().min(1),
  is_synthetic: z.boolean(),
});

export const PersonSchema = z.object({
  id: Id,
  name: z.string().min(1),
  role: RoleSchema,
  project_ids: z.array(Id),
  is_synthetic: z.boolean(),
});

/** Período de relato. Distinto do ano-base fiscal e do ano de envio. */
export const ReportingPeriodSchema = z.object({
  id: Id,
  project_id: Id,
  label: z.string().min(1),
  start: z.iso.date(),
  end: z.iso.date(),
  timezone: z.string().min(1),
  cadence: z.enum(["weekly", "monthly"]),
});

export const EvidenceSourceSchema = z.enum(["github", "upload", "notion", "researcher_statement"]);

export const EvidenceVersionSchema = z.object({
  id: Id,
  source: EvidenceSourceSchema,
  external_id: z.string().min(1),
  title: z.string().min(1),
  revision: z.string().min(1),
  content_hash: z.string().min(1),
  captured_at: Timestamp,
  author: z.string().nullable(),
  locator: z.string().nullable(),
  excerpt: z.string().nullable(),
  is_synthetic: z.boolean(),
});

export const ClaimStatusSchema = z.enum(["supported", "pending", "disputed"]);

export const ClaimSchema = z.object({
  id: Id,
  // As cinco últimas são as seções reais do backend (`ClaimSection`, #39).
  section: z.enum([
    "activity",
    "experiment",
    "result",
    "hours",
    "next_steps",
    "technological_challenge",
    "hypothesis",
    "method",
    "uncertainty",
  ]),
  text: z.string().min(1),
  status: ClaimStatusSchema,
  evidence_ids: z.array(Id),
  /** `null` quando a fonte não traz justificativa por afirmação (API real). */
  justification: z.string().min(1).nullable(),
  corrected_by_human: z.boolean(),
});

export const GapSchema = z.object({
  id: Id,
  /** Afirmação pendente que esta lacuna explica, se houver. */
  claim_id: Id.nullable(),
  description: z.string().min(1),
  question: z.string().min(1),
});

export const ReviewStateSchema = z.enum([
  "draft",
  "awaiting_researcher",
  "awaiting_manager",
  "available_to_fiscal",
  // API real (#39): texto aprovado por pesquisador e gerente na versão atual. Não é o
  // gate de encaminhamento ao fiscal, que continua sendo do backend.
  "text_approved",
  // API real: versão que já foi substituída por outra mais nova.
  "superseded",
]);

export const ReportVersionSchema = z.object({
  id: Id,
  report_id: Id,
  kind: z.enum(["individual", "managerial", "fiscal"]),
  project_id: Id,
  period_id: Id,
  author_id: Id,
  version: z.number().int().positive(),
  created_at: Timestamp,
  review_state: ReviewStateSchema,
  claims: z.array(ClaimSchema),
  gaps: z.array(GapSchema),
  change_summary: z.string().nullable(),
  stale: z.boolean(),
  stale_reason: z.string().nullable(),
});

export const ReviewSchema = z.object({
  id: Id,
  report_version_id: Id,
  reviewer_id: Id,
  role: RoleSchema,
  decision: z.enum(["approve", "request_changes"]),
  /** `null` quando a fonte só informa o estado da revisão (API real, `ReportStatus`). */
  justification: z.string().min(1).nullable(),
  created_at: Timestamp.nullable(),
});

export const ReportSummarySchema = z.object({
  report_id: Id,
  author_id: Id,
  author_name: z.string().min(1),
  latest_version_id: Id,
  latest_version: z.number().int().positive(),
  review_state: ReviewStateSchema,
  approved_by_researcher: z.boolean(),
  pending_claims: z.number().int().nonnegative(),
  open_gaps: z.number().int().nonnegative(),
  stale: z.boolean(),
});

export const ReportDetailSchema = z.object({
  version: ReportVersionSchema,
  /** Rótulo do período desta versão, para a tela não depender do contexto do projeto. */
  period_label: z.string().min(1),
  latest_version: z.number().int().positive(),
  history: z.array(
    z.object({ id: Id, version: z.number().int().positive(), created_at: Timestamp }),
  ),
  reviews: z.array(ReviewSchema),
  evidence: z.array(EvidenceVersionSchema),
});

export const RunStatusSchema = z.enum(["queued", "running", "awaiting_input", "completed", "failed"]);

export const RunSchema = z.object({
  id: Id,
  kind: z.enum(["closing", "reanalysis"]),
  status: RunStatusSchema,
  message: z.string().nullable(),
  created_at: Timestamp,
  updated_at: Timestamp,
  error: ApiErrorSchema.nullable(),
});

export const PendingTargetSchema = z.object({
  type: z.enum(["report", "expense", "finding"]),
  id: Id,
  label: z.string().min(1),
});

export const PendingRequestSchema = z.object({
  id: Id,
  target: PendingTargetSchema,
  reason: z.string().min(1),
  evidence_needed: z.string().min(1),
  requested_by_role: RoleSchema,
  assignee_role: RoleSchema,
  assignee_id: Id.nullable(),
  status: z.enum(["open", "answered", "resolved"]),
  response: z.string().nullable(),
  created_at: Timestamp,
});

export const ConsolidationSchema = z.object({
  project_id: Id,
  period_id: Id,
  reports: z.array(ReportSummarySchema),
  highlights: z.array(z.string()),
  problems: z.array(z.string()),
  open_requests: z.array(PendingRequestSchema),
  /** Gate calculado pelo backend; a UI apenas exibe. */
  can_forward: z.boolean(),
  blocking_reasons: z.array(z.string()),
  forwarded_at: Timestamp.nullable(),
  last_run: RunSchema.nullable(),
});

export const AllocationSchema = z.object({
  target_label: z.string().min(1),
  share: DecimalString.nullable(),
  basis: z.string().nullable(),
});

export const ExpenseSchema = z.object({
  id: Id,
  document: z.string().min(1),
  item: z.string().min(1),
  /** Ausência de valor permanece `null` — nunca vira zero. */
  amount: DecimalString.nullable(),
  currency: z.string().length(3),
  reconciliation_state: z.enum(["unreconciled", "matched", "duplicate_suspected", "excluded"]),
  allocations: z.array(AllocationSchema),
  excluded_reason: z.string().nullable(),
  evidence_ids: z.array(Id),
  is_synthetic: z.boolean(),
});

export const FindingSignalSchema = z.enum([
  "supported_by_evidence",
  "insufficient_information",
  "possible_incompatibility",
  "fiscal_judgment_required",
]);

export const FindingSchema = z.object({
  id: Id,
  criterion: z.object({
    code: z.string().min(1),
    title: z.string().min(1),
    reference: z.string().min(1),
    version: z.string().min(1),
  }),
  object: z.object({ type: z.enum(["activity", "expense"]), id: Id, label: z.string().min(1) }),
  signal: FindingSignalSchema,
  evidence_ids: z.array(Id),
  justification: z.string().min(1),
  gaps: z.array(z.string()),
  next_step: z.string().min(1),
  awaiting_reanalysis: z.boolean(),
});

/** Decisão fiscal humana: registro separado do finding. */
export const FiscalDecisionSchema = z.object({
  id: Id,
  finding_id: Id,
  decided_by: Id,
  decision: z.enum(["agree", "disagree", "defer"]),
  note: z.string().min(1),
  created_at: Timestamp,
});

export const FiscalPackageSchema = z.object({
  project_id: Id,
  period_id: Id,
  available: z.boolean(),
  forwarded_at: Timestamp.nullable(),
  report_versions: z.array(
    z.object({ id: Id, report_id: Id, author_name: z.string().min(1), version: z.number().int() }),
  ),
  stale: z.boolean(),
  stale_reason: z.string().nullable(),
  expenses: z.array(ExpenseSchema),
  findings: z.array(FindingSchema),
  decisions: z.array(FiscalDecisionSchema),
  open_requests: z.array(PendingRequestSchema),
  evidence: z.array(EvidenceVersionSchema),
  last_run: RunSchema.nullable(),
});

export type Role = z.infer<typeof RoleSchema>;
export type ApiError = z.infer<typeof ApiErrorSchema>;
export type Project = z.infer<typeof ProjectSchema>;
export type Person = z.infer<typeof PersonSchema>;
export type ReportingPeriod = z.infer<typeof ReportingPeriodSchema>;
export type EvidenceVersion = z.infer<typeof EvidenceVersionSchema>;
export type Claim = z.infer<typeof ClaimSchema>;
export type ClaimStatus = z.infer<typeof ClaimStatusSchema>;
export type Gap = z.infer<typeof GapSchema>;
export type ReviewState = z.infer<typeof ReviewStateSchema>;
export type ReportVersion = z.infer<typeof ReportVersionSchema>;
export type Review = z.infer<typeof ReviewSchema>;
export type ReportSummary = z.infer<typeof ReportSummarySchema>;
export type ReportDetail = z.infer<typeof ReportDetailSchema>;
export type RunStatus = z.infer<typeof RunStatusSchema>;
export type Run = z.infer<typeof RunSchema>;
export type PendingTarget = z.infer<typeof PendingTargetSchema>;
export type PendingRequest = z.infer<typeof PendingRequestSchema>;
export type Consolidation = z.infer<typeof ConsolidationSchema>;
export type Allocation = z.infer<typeof AllocationSchema>;
export type Expense = z.infer<typeof ExpenseSchema>;
export type FindingSignal = z.infer<typeof FindingSignalSchema>;
export type Finding = z.infer<typeof FindingSchema>;
export type FiscalDecision = z.infer<typeof FiscalDecisionSchema>;
export type FiscalPackage = z.infer<typeof FiscalPackageSchema>;
