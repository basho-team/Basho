/**
 * Fonte de dados real, via BFF (`app/api/bff`). O navegador nunca fala direto com o
 * backend nem conhece o segredo de identidade do revisor.
 *
 * Implementado: relatório (versões e histórico), revisão e correção (#39); pendências,
 * resposta, aprovação formal e dossiê (#5). Toda chamada declara o papel da demonstração
 * (`X-Demo-Role`), e o BFF injeta a identidade. O que ainda não tem rota no backend
 * (contexto, consolidação, fiscal) falha de forma explícita em vez de fingir dados.
 */
import type { z } from "zod";
import {
  ApprovalSchema,
  DossierSchema,
  PendingAnswerOutSchema,
  PendingPageSchema,
  type ApiPendingItem,
} from "@/lib/api/projects";
import { ApiReportVersionOutSchema, ApiReviewOutSchema, type ApiReportVersionOut } from "@/lib/api/reports";
import {
  BffErrorCode,
  bffPaths,
  DEMO_ROLE_HEADER,
  MAX_PENDING_PAGE,
  ReviewerRoleSchema,
  type BffReviewRequest,
  type ReviewerRole,
} from "@/lib/bff/contract";
import { ApiErrorSchema, type PendingRequest, type Role } from "@/lib/contracts/provisional";
import { toPendingRequest, toReportDetail, toReview } from "@/lib/data/api-adapters";
import {
  DataSourceError,
  type ArtifactDecisionInput,
  type CorrectionInput,
  type DataSource,
  type RespondPendingInput,
  type ReviewInput,
} from "@/lib/data/source";
import { currentDemoRole } from "@/lib/demo/role";

/** Teto de versões percorridas pela cadeia `supersedes_id` (proteção contra ciclo). */
const MAX_SERIES_LENGTH = 50;
/** Teto de páginas de pendências lidas de uma vez (10 × 200). */
const MAX_PENDING_PAGES = 10;
const UNEXPECTED_RESPONSE = "Resposta inesperada do servidor.";

export interface ApiSourceOptions {
  fetch?: typeof fetch;
  /** Projeto da demonstração (`NEXT_PUBLIC_BASHO_PROJECT_ID`). */
  projectId?: string;
  /** Papel da troca de papel da demo; por padrão, o da rota atual. */
  currentRole?: () => ReviewerRole | null;
}

function clientError(code: string, message: string, retryable = false): DataSourceError {
  return new DataSourceError({ code, message, correlation_id: `ui-${Date.now()}`, retryable });
}

function notImplemented(operation: string): Promise<never> {
  return Promise.reject(
    clientError(
      "NOT_IMPLEMENTED",
      `A operação "${operation}" ainda não existe na API. Use NEXT_PUBLIC_DATA_SOURCE=mock para a demonstração.`,
    ),
  );
}

function reviewerRole(role: Role) {
  const parsed = ReviewerRoleSchema.safeParse(role);
  if (!parsed.success) throw clientError(BffErrorCode.forbidden, "Este papel não pode revisar relatórios.");
  return parsed.data;
}

export function createApiSource(options: ApiSourceOptions = {}): DataSource {
  const doFetch = options.fetch ?? ((input, init) => fetch(input, init));
  const currentRole = options.currentRole ?? currentDemoRole;

  async function request<S extends z.ZodType>(url: string, init: RequestInit, schema: S): Promise<z.output<S>> {
    const role = currentRole();
    const headers = { Accept: "application/json", ...(role ? { [DEMO_ROLE_HEADER]: role } : {}), ...init.headers };
    let res: Response;
    try {
      res = await doFetch(url, { ...init, cache: "no-store", headers });
    } catch {
      throw clientError(BffErrorCode.backendUnavailable, "Sem conexão com o servidor. Tente de novo.", true);
    }
    const body: unknown = await res.json().catch(() => null);
    if (!res.ok) {
      const error = ApiErrorSchema.safeParse(body);
      throw error.success ? new DataSourceError(error.data) : clientError(BffErrorCode.invalidResponse, UNEXPECTED_RESPONSE, true);
    }
    const parsed = schema.safeParse(body);
    if (!parsed.success) throw clientError(BffErrorCode.invalidResponse, UNEXPECTED_RESPONSE);
    return parsed.data;
  }

  const getVersion = (versionId: string) => request(bffPaths.report(versionId), { method: "GET" }, ApiReportVersionOutSchema);

  const postJson = <S extends z.ZodType>(url: string, body: unknown, schema: S) =>
    request(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }, schema);

  const postReview = (versionId: string, body: BffReviewRequest) => postJson(bffPaths.review(versionId), body, ApiReviewOutSchema);

  function projectId(): string {
    if (options.projectId) return options.projectId;
    throw clientError("NOT_CONFIGURED", "Defina NEXT_PUBLIC_BASHO_PROJECT_ID com o projeto da demonstração.");
  }

  async function listAllPending(): Promise<ApiPendingItem[]> {
    const pid = projectId();
    const items: ApiPendingItem[] = [];
    let offset: number | null = 0;
    for (let page = 0; offset !== null && page < MAX_PENDING_PAGES; page += 1) {
      const result: z.output<typeof PendingPageSchema> = await request(
        bffPaths.pending(pid, { limit: MAX_PENDING_PAGE, offset }),
        { method: "GET" },
        PendingPageSchema,
      );
      items.push(...result.items);
      offset = result.next_offset;
    }
    return items;
  }

  /** Pendências do papel, abertas ou respondidas. Quem é o designado vem do backend. */
  async function listPendingFor(role: Role): Promise<PendingRequest[]> {
    const items = await listAllPending();
    return items
      .map(toPendingRequest)
      .filter((p): p is PendingRequest => p !== null && p.assignee_role === role && p.status !== "resolved");
  }

  async function respondPending(input: RespondPendingInput): Promise<PendingRequest> {
    const out = await postJson(bffPaths.answer(input.requestId), { answer: input.response }, PendingAnswerOutSchema);
    const mapped = toPendingRequest(out.pending);
    if (!mapped) throw clientError(BffErrorCode.invalidResponse, UNEXPECTED_RESPONSE);
    return mapped;
  }

  const decideArtifact = (input: ArtifactDecisionInput) =>
    postJson(bffPaths.approval(input.artifactId), { decision: input.decision, comment: input.comment }, ApprovalSchema);

  const getDossier = () => request(bffPaths.dossier(projectId()), { method: "GET" }, DossierSchema);

  /** Carrega a série inteira a partir de qualquer versão: a atual e a cadeia `supersedes_id`. */
  async function loadSeries(anyVersionId: string): Promise<ApiReportVersionOut[]> {
    const first = await getVersion(anyVersionId);
    const byId = new Map<string, ApiReportVersionOut>([[first.version.id, first]]);
    const visited = new Set<string>();
    let cursor: ApiReportVersionOut | undefined = first.is_current ? first : await getVersion(first.current_version_id);
    while (cursor && !visited.has(cursor.version.id) && visited.size < MAX_SERIES_LENGTH) {
      visited.add(cursor.version.id);
      byId.set(cursor.version.id, cursor);
      const previous: string | null | undefined = cursor.version.supersedes_id;
      cursor = previous ? (byId.get(previous) ?? (await getVersion(previous))) : undefined;
    }
    return [...byId.values()];
  }

  /** `reportId` é qualquer versão da série. Sem `version`, mostra a atual (como no mock). */
  async function getReport(reportId: string, version?: number) {
    const series = await loadSeries(reportId);
    const current = series.find((out) => out.is_current) ?? series[0];
    const selected = version === undefined ? current : series.find((out) => out.version.number === version);
    if (!selected) throw clientError(BffErrorCode.notFound, `Versão ${version} do relatório não encontrada.`);
    return toReportDetail(reportId, series, selected);
  }

  async function submitReview(input: ReviewInput) {
    const out = await postReview(input.reportVersionId, {
      reviewer_id: input.reviewerId,
      role: reviewerRole(input.role),
      decision: input.decision === "approve" ? "text_approved" : "changes_requested",
      comment: input.justification.trim() || null,
    });
    return toReview(out);
  }

  /** Correção = revisão `changes_requested` com `revise_claim`; o backend cria a versão N+1. */
  async function submitCorrection(input: CorrectionInput) {
    const role = reviewerRole(input.role);
    const out = await getVersion(input.reportVersionId);
    const index = out.version.claim_ids.indexOf(input.claimId);
    const claim = index >= 0 ? out.version.draft.claims[index] : undefined;
    if (!claim) throw clientError(BffErrorCode.notFound, "Afirmação não encontrada nesta versão.");
    await postReview(input.reportVersionId, {
      reviewer_id: input.reviewerId,
      role,
      decision: "changes_requested",
      comment: null,
      correction: {
        reason: input.justification,
        operations: [
          {
            kind: "revise_claim",
            claim_id: input.claimId,
            text: input.newText,
            status: claim.status,
            evidence_ids: claim.evidence_ids,
            question: claim.question ?? null,
            ask_role: claim.ask_role ?? null,
            dispute_reason: claim.dispute_reason ?? null,
          },
        ],
      },
    });
    return getReport(input.reportVersionId);
  }

  return {
    kind: "api",
    getContext: () => notImplemented("getContext"),
    listReports: () => notImplemented("listReports"),
    getReport,
    submitReview,
    submitCorrection,
    getConsolidation: () => notImplemented("getConsolidation"),
    requestClarification: () => notImplemented("requestClarification"),
    triggerClosing: () => notImplemented("triggerClosing"),
    getRun: () => notImplemented("getRun"),
    forwardToFiscal: () => notImplemented("forwardToFiscal"),
    getFiscalPackage: () => notImplemented("getFiscalPackage"),
    recordFiscalDecision: () => notImplemented("recordFiscalDecision"),
    returnPending: () => notImplemented("returnPending"),
    listPendingFor,
    respondPending,
    decideArtifact,
    getDossier,
  };
}
