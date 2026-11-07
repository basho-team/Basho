import type {
  ApiError,
  Consolidation,
  FiscalDecision,
  FiscalPackage,
  PendingRequest,
  Person,
  Project,
  ReportDetail,
  ReportingPeriod,
  ReportSummary,
  Review,
  Role,
  Run,
} from "@/lib/contracts/provisional";

/** Erro estruturado vindo da fonte de dados (mock ou API). Nunca contém segredos. */
export class DataSourceError extends Error {
  readonly error: ApiError;

  constructor(error: ApiError) {
    super(error.message);
    this.name = "DataSourceError";
    this.error = error;
  }
}

export interface ProjectContext {
  project: Project;
  period: ReportingPeriod;
  people: Person[];
}

export interface ReviewInput {
  reportVersionId: string;
  reviewerId: string;
  role: Role;
  decision: Review["decision"];
  justification: string;
}

export interface CorrectionInput {
  reportVersionId: string;
  claimId: string;
  newText: string;
  justification: string;
}

export interface ClarificationInput {
  reportId: string;
  question: string;
}

export interface FiscalDecisionInput {
  findingId: string;
  decidedBy: string;
  decision: FiscalDecision["decision"];
  note: string;
}

export interface ReturnPendingInput {
  findingId: string;
  assigneeRole: Exclude<Role, "fiscal">;
  reason: string;
  evidenceNeeded: string;
}

export interface RespondPendingInput {
  requestId: string;
  respondedBy: string;
  response: string;
}

/**
 * Operações da UI (CONTRATOS.md § "API a detalhar"). Único ponto de troca mock ↔ API.
 */
export interface DataSource {
  readonly kind: "mock" | "api";
  getContext(): Promise<ProjectContext>;
  listReports(periodId: string): Promise<ReportSummary[]>;
  getReport(reportId: string, version?: number): Promise<ReportDetail>;
  submitReview(input: ReviewInput): Promise<Review>;
  submitCorrection(input: CorrectionInput): Promise<ReportDetail>;
  getConsolidation(periodId: string): Promise<Consolidation>;
  requestClarification(input: ClarificationInput): Promise<PendingRequest>;
  triggerClosing(periodId: string): Promise<Run>;
  getRun(runId: string): Promise<Run>;
  forwardToFiscal(periodId: string): Promise<Consolidation>;
  getFiscalPackage(periodId: string): Promise<FiscalPackage>;
  recordFiscalDecision(input: FiscalDecisionInput): Promise<FiscalDecision>;
  returnPending(input: ReturnPendingInput): Promise<PendingRequest>;
  listPendingFor(role: Role, personId?: string): Promise<PendingRequest[]>;
  respondPending(input: RespondPendingInput): Promise<PendingRequest>;
}
