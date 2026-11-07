/**
 * SIMULAÇÃO do backend para a demo. Não é regra de produto: gates, reanálises e versões
 * aqui só imitam o comportamento esperado (EXECUCAO_E_ACEITE.md § Aceite) até a API real
 * existir. Todas as funções são puras e retornam um novo estado.
 */
import {
  EvidenceVersionSchema,
  ExpenseSchema,
  FindingSchema,
  ReportVersionSchema,
  ReviewSchema,
  type EvidenceVersion,
  type Expense,
  type Finding,
  type FiscalDecision,
  type PendingRequest,
  type ReportVersion,
  type Review,
  type Run,
} from "@/lib/contracts/provisional";
import {
  EVIDENCE,
  EXPENSES,
  FINDINGS,
  PEOPLE,
  REPORT_VERSIONS,
  REVIEWS,
} from "@/lib/data/mock-fixtures";
import { DataSourceError } from "@/lib/data/source";

export const RUN_QUEUED_MS = 800;
export const RUN_RUNNING_MS = 2500;

export type RunEffect = { type: "reanalysis"; requestId: string; evidenceId: string };

export interface MockRun {
  id: string;
  kind: Run["kind"];
  startedAtMs: number;
  effect: RunEffect | null;
  effectApplied: boolean;
}

export interface MockState {
  evidence: EvidenceVersion[];
  reportVersions: ReportVersion[];
  reviews: Review[];
  requests: PendingRequest[];
  expenses: Expense[];
  findings: Finding[];
  decisions: FiscalDecision[];
  runs: MockRun[];
  forwarded: { at: string; versionIds: string[] } | null;
  seq: number;
}

export function createInitialState(): MockState {
  return {
    evidence: EvidenceVersionSchema.array().parse(EVIDENCE),
    reportVersions: ReportVersionSchema.array().parse(REPORT_VERSIONS),
    reviews: ReviewSchema.array().parse(REVIEWS),
    requests: [],
    expenses: ExpenseSchema.array().parse(EXPENSES),
    findings: FindingSchema.array().parse(FINDINGS),
    decisions: [],
    runs: [],
    forwarded: null,
    seq: 1,
  };
}

export function fail(code: string, message: string, retryable = false): never {
  throw new DataSourceError({ code, message, retryable, correlation_id: `mock-${Date.now()}` });
}

export function iso(nowMs: number): string {
  return new Date(nowMs).toISOString();
}

export function nextId(state: MockState, prefix: string): [string, MockState] {
  return [`${prefix}-${state.seq}`, { ...state, seq: state.seq + 1 }];
}

export function personName(id: string | null): string {
  return PEOPLE.find((p) => p.id === id)?.name ?? "desconhecido";
}

export function personByRole(role: string): string {
  return PEOPLE.find((p) => p.role === role)?.id ?? "desconhecido";
}

export function reportIds(state: MockState): string[] {
  return [...new Set(state.reportVersions.map((v) => v.report_id))];
}

export function latestVersion(state: MockState, reportId: string): ReportVersion {
  const versions = state.reportVersions.filter((v) => v.report_id === reportId);
  if (versions.length === 0) fail("NOT_FOUND", `Relatório ${reportId} não encontrado.`);
  return versions.reduce((a, b) => (b.version > a.version ? b : a));
}

export function findVersion(state: MockState, versionId: string): ReportVersion {
  const version = state.reportVersions.find((v) => v.id === versionId);
  if (!version) fail("NOT_FOUND", `Versão ${versionId} não encontrada.`);
  return version;
}

export function isApprovedByResearcher(state: MockState, version: ReportVersion): boolean {
  return state.reviews.some(
    (r) => r.report_version_id === version.id && r.role === "researcher" && r.decision === "approve",
  );
}

export function runStatus(run: MockRun, nowMs: number): Run["status"] {
  const elapsed = nowMs - run.startedAtMs;
  if (elapsed < RUN_QUEUED_MS) return "queued";
  if (elapsed < RUN_RUNNING_MS) return "running";
  return "completed";
}

export function toRun(run: MockRun, nowMs: number): Run {
  const status = runStatus(run, nowMs);
  const messages: Record<Run["status"], string> = {
    queued: "Na fila",
    running: run.kind === "closing" ? "Consolidando relatórios do período" : "Reavaliando objetos afetados",
    awaiting_input: "Aguardando resposta humana",
    completed: run.kind === "closing" ? "Fechamento concluído" : "Reanálise concluída",
    failed: "Falhou",
  };
  return {
    id: run.id,
    kind: run.kind,
    status,
    message: messages[status],
    created_at: iso(run.startedAtMs),
    updated_at: iso(Math.min(nowMs, run.startedAtMs + RUN_RUNNING_MS)),
    error: null,
  };
}

/** Cria a versão N+1 de um relatório. Aprovações antigas não valem para a nova versão. */
export function appendVersion(
  state: MockState,
  base: ReportVersion,
  changes: Pick<ReportVersion, "claims" | "gaps" | "change_summary">,
  nowMs: number,
): [ReportVersion, MockState] {
  const [id, next] = nextId(state, `rv-${base.report_id}`);
  const version: ReportVersion = {
    ...base,
    ...changes,
    id,
    version: base.version + 1,
    created_at: iso(nowMs),
    review_state: "awaiting_researcher",
    stale: false,
    stale_reason: null,
  };
  return [version, { ...next, reportVersions: [...next.reportVersions, version] }];
}
