/**
 * Fonte de dados SIMULADA (modo demonstração). Mantém o estado em memória do navegador,
 * simula latência e permite injetar falhas por operação (`?falha=submitReview`).
 * Recarregar a página volta ao cenário inicial.
 */
import {
  ConsolidationSchema,
  FiscalDecisionSchema,
  FiscalPackageSchema,
  PendingRequestSchema,
  ReportDetailSchema,
  ReportSummarySchema,
  ReviewSchema,
  RunSchema,
} from "@/lib/contracts/provisional";
import { DossierSchema } from "@/lib/api/projects";
import { mockDossier } from "@/lib/data/mock-dossier";
import { PEOPLE, PERIOD, PROJECT } from "@/lib/data/mock-fixtures";
import {
  advance,
  applyClarification,
  applyCorrection,
  applyFiscalDecision,
  applyForward,
  applyRespond,
  applyReturnPending,
  applyReview,
  startRun,
} from "@/lib/data/mock-operations";
import { createInitialState, fail, toRun, type MockState } from "@/lib/data/mock-state";
import { consolidation, fiscalPackage, reportDetail, summaries } from "@/lib/data/mock-views";
import type { DataSource } from "@/lib/data/source";

const DEFAULT_LATENCY_MS = 350;

export interface MockSourceOptions {
  now?: () => number;
  latencyMs?: number;
  /** Operações que devem falhar (erro recuperável simulado). */
  failures?: () => readonly string[];
}

function failuresFromUrl(): readonly string[] {
  if (typeof window === "undefined") return [];
  return new URLSearchParams(window.location.search).getAll("falha");
}

export function createMockSource(options: MockSourceOptions = {}): DataSource {
  const now = options.now ?? Date.now;
  const latencyMs = options.latencyMs ?? DEFAULT_LATENCY_MS;
  const failures = options.failures ?? failuresFromUrl;
  let state: MockState = createInitialState();

  async function run<T>(operation: string, fn: (current: MockState, nowMs: number) => [T, MockState]): Promise<T> {
    if (latencyMs > 0) await new Promise((resolve) => setTimeout(resolve, latencyMs));
    if (failures().includes(operation)) {
      fail("SIMULATED_FAILURE", `Falha em "${operation}". Tente novamente.`, true);
    }
    const nowMs = now();
    const [result, next] = fn(advance(state, nowMs), nowMs);
    state = next;
    return result;
  }

  const read = <T>(operation: string, fn: (current: MockState, nowMs: number) => T) =>
    run(operation, (current, nowMs) => [fn(current, nowMs), current]);

  return {
    kind: "mock",
    getContext: () => read("getContext", () => ({ project: PROJECT, period: PERIOD, people: PEOPLE })),
    listReports: () => read("listReports", (s) => ReportSummarySchema.array().parse(summaries(s))),
    getReport: (reportId, version) =>
      read("getReport", (s) => ReportDetailSchema.parse(reportDetail(s, reportId, version))),
    submitReview: (input) =>
      run("submitReview", (s, t) => {
        const [review, next] = applyReview(s, input, t);
        return [ReviewSchema.parse(review), next];
      }),
    submitCorrection: (input) =>
      run("submitCorrection", (s, t) => {
        const [version, next] = applyCorrection(s, input, t);
        return [ReportDetailSchema.parse(reportDetail(next, version.report_id)), next];
      }),
    getConsolidation: () => read("getConsolidation", (s, t) => ConsolidationSchema.parse(consolidation(s, t))),
    requestClarification: (input) =>
      run("requestClarification", (s, t) => {
        const [request, next] = applyClarification(s, input, t);
        return [PendingRequestSchema.parse(request), next];
      }),
    triggerClosing: () =>
      run("triggerClosing", (s, t) => {
        const [created, next] = startRun(s, "closing", t);
        return [RunSchema.parse(created), next];
      }),
    getRun: (runId) =>
      read("getRun", (s, t) => {
        const found = s.runs.find((r) => r.id === runId);
        if (!found) fail("NOT_FOUND", "Execução não encontrada.");
        return RunSchema.parse(toRun(found, t));
      }),
    forwardToFiscal: () =>
      run("forwardToFiscal", (s, t) => {
        const next = applyForward(s, t);
        return [ConsolidationSchema.parse(consolidation(next, t)), next];
      }),
    getFiscalPackage: () => read("getFiscalPackage", (s, t) => FiscalPackageSchema.parse(fiscalPackage(s, t))),
    recordFiscalDecision: (input) =>
      run("recordFiscalDecision", (s, t) => {
        const [decision, next] = applyFiscalDecision(s, input, t);
        return [FiscalDecisionSchema.parse(decision), next];
      }),
    returnPending: (input) =>
      run("returnPending", (s, t) => {
        const [request, next] = applyReturnPending(s, input, t);
        return [PendingRequestSchema.parse(request), next];
      }),
    listPendingFor: (role, personId) =>
      read("listPendingFor", (s) =>
        PendingRequestSchema.array().parse(
          s.requests.filter(
            (r) =>
              r.assignee_role === role &&
              r.status !== "resolved" &&
              (personId === undefined || r.assignee_id === null || r.assignee_id === personId),
          ),
        ),
      ),
    respondPending: (input) =>
      run("respondPending", (s, t) => {
        const [request, next] = applyRespond(s, input, t);
        return [PendingRequestSchema.parse(request), next];
      }),
    // A simulação não tem artefatos do Maker com veredito: a aprovação formal só existe na API.
    decideArtifact: () =>
      read("decideArtifact", () =>
        fail("NOT_AVAILABLE_IN_MOCK", "A aprovação formal de artefatos só existe com NEXT_PUBLIC_DATA_SOURCE=api."),
      ),
    getDossier: () => read("getDossier", () => DossierSchema.parse(mockDossier())),
  };
}
