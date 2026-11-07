/** SIMULAÇÃO: transições de escrita. Cada função recebe o estado e devolve um novo estado. */
import type {
  FiscalDecision,
  PendingRequest,
  ReportVersion,
  Review,
  Run,
} from "@/lib/contracts/provisional";
import { REANALYSIS_OUTCOMES } from "@/lib/data/mock-reanalysis";
import {
  appendVersion,
  fail,
  findVersion,
  iso,
  latestVersion,
  nextId,
  personByRole,
  personName,
  runStatus,
  toRun,
  type MockState,
} from "@/lib/data/mock-state";
import { consolidation } from "@/lib/data/mock-views";
import type {
  ClarificationInput,
  CorrectionInput,
  FiscalDecisionInput,
  RespondPendingInput,
  ReturnPendingInput,
  ReviewInput,
} from "@/lib/data/source";

type Result<T> = [T, MockState];

function assertLatest(state: MockState, version: ReportVersion): void {
  const latest = latestVersion(state, version.report_id);
  if (latest.id !== version.id) {
    fail(
      "VERSION_CONFLICT",
      `Você está vendo a v${version.version}, mas já existe a v${latest.version}. Revise a versão atual.`,
    );
  }
}

function replaceVersion(state: MockState, updated: ReportVersion): MockState {
  return {
    ...state,
    reportVersions: state.reportVersions.map((v) => (v.id === updated.id ? updated : v)),
  };
}

export function applyReview(state: MockState, input: ReviewInput, nowMs: number): Result<Review> {
  const version = findVersion(state, input.reportVersionId);
  assertLatest(state, version);
  if (input.role === "researcher" && input.reviewerId !== version.author_id) {
    fail("FORBIDDEN", "Só o autor do relatório pode aprová-lo como pesquisador.");
  }
  const [id, next] = nextId(state, "rev");
  const review: Review = {
    id,
    report_version_id: version.id,
    reviewer_id: input.reviewerId,
    role: input.role,
    decision: input.decision,
    justification: input.justification,
    created_at: iso(nowMs),
  };
  const reviewState = input.decision === "approve" ? "awaiting_manager" : "awaiting_researcher";
  const withReview = { ...next, reviews: [...next.reviews, review] };
  return [review, replaceVersion(withReview, { ...version, review_state: reviewState })];
}

export function applyCorrection(
  state: MockState,
  input: CorrectionInput,
  nowMs: number,
): Result<ReportVersion> {
  const version = findVersion(state, input.reportVersionId);
  assertLatest(state, version);
  if (!version.claims.some((c) => c.id === input.claimId)) {
    fail("NOT_FOUND", "Afirmação não encontrada nesta versão.");
  }
  const claims = version.claims.map((c) =>
    c.id === input.claimId ? { ...c, text: input.newText, corrected_by_human: true } : c,
  );
  return appendVersion(
    state,
    version,
    { claims, gaps: version.gaps, change_summary: `Correção do pesquisador: ${input.justification}` },
    nowMs,
  );
}

export function applyClarification(
  state: MockState,
  input: ClarificationInput,
  nowMs: number,
): Result<PendingRequest> {
  const latest = latestVersion(state, input.reportId);
  const [id, next] = nextId(state, "req");
  const request: PendingRequest = {
    id,
    target: { type: "report", id: input.reportId, label: `Relatório de ${personName(latest.author_id)}` },
    reason: input.question,
    evidence_needed: "Resposta do pesquisador, com fonte quando houver.",
    requested_by_role: "manager",
    assignee_role: "researcher",
    assignee_id: latest.author_id,
    status: "open",
    response: null,
    created_at: iso(nowMs),
  };
  return [request, { ...next, requests: [...next.requests, request] }];
}

export function startRun(
  state: MockState,
  kind: Run["kind"],
  nowMs: number,
  effect: MockState["runs"][number]["effect"] = null,
): Result<Run> {
  const [id, next] = nextId(state, "run");
  const run = { id, kind, startedAtMs: nowMs, effect, effectApplied: false };
  return [toRun(run, nowMs), { ...next, runs: [...next.runs, run] }];
}

export function applyForward(state: MockState, nowMs: number): MockState {
  const view = consolidation(state, nowMs);
  if (!view.can_forward) {
    fail("FORWARD_BLOCKED", `Encaminhamento bloqueado: ${view.blocking_reasons.join("; ")}`);
  }
  const ids = view.reports.map((r) => r.latest_version_id);
  const reportVersions = state.reportVersions.map((v) =>
    ids.includes(v.id) ? { ...v, review_state: "available_to_fiscal" as const } : v,
  );
  return { ...state, reportVersions, forwarded: { at: iso(nowMs), versionIds: ids } };
}

export function applyFiscalDecision(
  state: MockState,
  input: FiscalDecisionInput,
  nowMs: number,
): Result<FiscalDecision> {
  if (!state.findings.some((f) => f.id === input.findingId)) {
    fail("NOT_FOUND", "Sinalização não encontrada.");
  }
  const [id, next] = nextId(state, "dec");
  const decision: FiscalDecision = {
    id,
    finding_id: input.findingId,
    decided_by: input.decidedBy,
    decision: input.decision,
    note: input.note,
    created_at: iso(nowMs),
  };
  return [decision, { ...next, decisions: [...next.decisions, decision] }];
}

function claimAuthor(state: MockState, claimId: string): string | null {
  const version = state.reportVersions.find((v) => v.claims.some((c) => c.id === claimId));
  return version?.author_id ?? null;
}

export function applyReturnPending(
  state: MockState,
  input: ReturnPendingInput,
  nowMs: number,
): Result<PendingRequest> {
  const finding = state.findings.find((f) => f.id === input.findingId);
  if (!finding) fail("NOT_FOUND", "Sinalização não encontrada.");
  const assigneeId =
    input.assigneeRole === "manager" ? personByRole("manager") : claimAuthor(state, finding.object.id);
  const [id, next] = nextId(state, "req");
  const request: PendingRequest = {
    id,
    target: { type: "finding", id: finding.id, label: finding.object.label },
    reason: input.reason,
    evidence_needed: input.evidenceNeeded,
    requested_by_role: "fiscal",
    assignee_role: input.assigneeRole,
    assignee_id: assigneeId,
    status: "open",
    response: null,
    created_at: iso(nowMs),
  };
  return [request, { ...next, requests: [...next.requests, request] }];
}

export function applyRespond(
  state: MockState,
  input: RespondPendingInput,
  nowMs: number,
): Result<PendingRequest> {
  const request = state.requests.find((r) => r.id === input.requestId);
  if (!request) fail("NOT_FOUND", "Pendência não encontrada.");
  if (request.status !== "open") fail("REQUEST_NOT_OPEN", "Esta pendência já foi respondida.");
  const [evidenceId, s1] = nextId(state, "ev-resp");
  const evidence = {
    id: evidenceId,
    source: "researcher_statement" as const,
    external_id: `resposta:${request.id}`,
    title: `Resposta de ${personName(input.respondedBy)} à pendência`,
    revision: "1",
    content_hash: `sha256:simulado-${evidenceId}`,
    captured_at: iso(nowMs),
    author: personName(input.respondedBy),
    locator: null,
    excerpt: input.response,
    synthetic: true,
  };
  const answered: PendingRequest = { ...request, status: "answered", response: input.response };
  const s2: MockState = {
    ...s1,
    evidence: [...s1.evidence, evidence],
    requests: s1.requests.map((r) => (r.id === request.id ? answered : r)),
    findings: s1.findings.map((f) =>
      request.target.type === "finding" && f.id === request.target.id
        ? { ...f, awaiting_reanalysis: true }
        : f,
    ),
  };
  const [, s3] = startRun(s2, "reanalysis", nowMs, {
    type: "reanalysis",
    requestId: request.id,
    evidenceId,
  });
  return [answered, s3];
}

/** Aplica os efeitos das reanálises que já terminaram (relógio injetado). */
export function advance(state: MockState, nowMs: number): MockState {
  return state.runs.reduce((acc, run) => {
    if (run.effectApplied || !run.effect || runStatus(run, nowMs) !== "completed") return acc;
    const applied = applyReanalysis(acc, run.effect.requestId, run.effect.evidenceId, nowMs);
    return {
      ...applied,
      runs: applied.runs.map((r) => (r.id === run.id ? { ...r, effectApplied: true } : r)),
    };
  }, state);
}

function applyReanalysis(state: MockState, requestId: string, evidenceId: string, nowMs: number): MockState {
  const request = state.requests.find((r) => r.id === requestId);
  if (!request) return state;
  const resolved = {
    ...state,
    requests: state.requests.map((r) => (r.id === requestId ? { ...r, status: "resolved" as const } : r)),
  };
  if (request.target.type === "report") {
    return updateReportFromResponse(resolved, request.target.id, null, request.response ?? "", evidenceId, nowMs);
  }
  const finding = resolved.findings.find((f) => f.id === request.target.id);
  if (!finding) return resolved;
  const outcome = REANALYSIS_OUTCOMES[finding.id] ?? REANALYSIS_OUTCOMES.default;
  const withFinding = {
    ...resolved,
    findings: resolved.findings.map((f) =>
      f.id === finding.id
        ? { ...f, ...outcome, evidence_ids: [...f.evidence_ids, evidenceId], awaiting_reanalysis: false }
        : f,
    ),
  };
  const reportId = withFinding.reportVersions.find((v) =>
    v.claims.some((c) => c.id === finding.object.id),
  )?.report_id;
  if (!reportId) return withFinding;
  return updateReportFromResponse(withFinding, reportId, finding.object.id, request.response ?? "", evidenceId, nowMs);
}

function updateReportFromResponse(
  state: MockState,
  reportId: string,
  claimId: string | null,
  response: string,
  evidenceId: string,
  nowMs: number,
): MockState {
  const latest = latestVersion(state, reportId);
  const answeredClaim = {
    id: claimId ?? `c-resp-${evidenceId}`,
    section: claimId ? (latest.claims.find((c) => c.id === claimId)?.section ?? "activity") : "activity",
    text: response,
    status: "supported" as const,
    evidence_ids: [evidenceId],
    justification: "Informação declarada pelo responsável em resposta à pendência.",
    corrected_by_human: true,
  };
  const claims = claimId
    ? latest.claims.map((c) => (c.id === claimId ? answeredClaim : c))
    : [...latest.claims, answeredClaim];
  const gaps = claimId ? latest.gaps.filter((g) => g.claim_id !== claimId) : latest.gaps;
  const [, next] = appendVersion(
    state,
    latest,
    { claims, gaps, change_summary: "Atualizado pela resposta à pendência; requer nova aprovação." },
    nowMs,
  );
  return next;
}
