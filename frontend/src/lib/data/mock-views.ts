/** SIMULAÇÃO: projeções de leitura que a API real deverá devolver prontas. */
import type {
  Consolidation,
  FiscalPackage,
  ReportDetail,
  ReportSummary,
  Run,
} from "@/lib/contracts/provisional";
import { HIGHLIGHTS, PERIOD, PROBLEMS } from "@/lib/data/mock-fixtures";
import {
  fail,
  isApprovedByResearcher,
  latestVersion,
  personName,
  reportIds,
  toRun,
  type MockState,
} from "@/lib/data/mock-state";

export function summaries(state: MockState): ReportSummary[] {
  return reportIds(state).map((reportId) => {
    const latest = latestVersion(state, reportId);
    return {
      report_id: reportId,
      author_id: latest.author_id,
      author_name: personName(latest.author_id),
      latest_version_id: latest.id,
      latest_version: latest.version,
      review_state: latest.review_state,
      approved_by_researcher: isApprovedByResearcher(state, latest),
      pending_claims: latest.claims.filter((c) => c.status !== "supported").length,
      open_gaps: latest.gaps.length,
      stale: latest.stale,
    };
  });
}

export function reportDetail(state: MockState, reportId: string, version?: number): ReportDetail {
  const all = state.reportVersions
    .filter((v) => v.report_id === reportId)
    .sort((a, b) => a.version - b.version);
  const latest = latestVersion(state, reportId);
  const selected = version === undefined ? latest : all.find((v) => v.version === version);
  if (!selected) fail("NOT_FOUND", `Versão ${version} do relatório não encontrada.`);
  const evidenceIds = new Set(selected.claims.flatMap((c) => c.evidence_ids));
  return {
    version: selected,
    latest_version: latest.version,
    history: all.map((v) => ({ id: v.id, version: v.version, created_at: v.created_at })),
    reviews: state.reviews.filter((r) => r.report_version_id === selected.id),
    evidence: state.evidence.filter((e) => evidenceIds.has(e.id)),
  };
}

function lastRun(state: MockState, kind: Run["kind"], nowMs: number): Run | null {
  const runs = state.runs.filter((r) => r.kind === kind);
  const last = runs[runs.length - 1];
  return last ? toRun(last, nowMs) : null;
}

function isForwardedCurrent(state: MockState): boolean {
  if (!state.forwarded) return false;
  const latestIds = reportIds(state).map((id) => latestVersion(state, id).id);
  const forwardedIds = state.forwarded.versionIds;
  return latestIds.every((id) => forwardedIds.includes(id));
}

export function blockingReasons(state: MockState): string[] {
  const unapproved = summaries(state)
    .filter((s) => !s.approved_by_researcher)
    .map((s) => `${s.author_name} v${s.latest_version}: aguardando aprovação do pesquisador`);
  const openOnReports = state.requests
    .filter((r) => r.target.type === "report" && r.status !== "resolved")
    .map((r) => `Pendência em aberto: ${r.target.label}`);
  return [...unapproved, ...openOnReports];
}

export function consolidation(state: MockState, nowMs: number): Consolidation {
  const reasons = blockingReasons(state);
  const alreadyCurrent = isForwardedCurrent(state);
  return {
    project_id: PERIOD.project_id,
    period_id: PERIOD.id,
    reports: summaries(state),
    highlights: HIGHLIGHTS,
    problems: PROBLEMS,
    open_requests: state.requests.filter((r) => r.status !== "resolved"),
    can_forward: reasons.length === 0 && !alreadyCurrent,
    blocking_reasons: alreadyCurrent ? ["As versões atuais já foram encaminhadas ao fiscal."] : reasons,
    forwarded_at: state.forwarded?.at ?? null,
    last_run: lastRun(state, "closing", nowMs),
  };
}

export function fiscalPackage(state: MockState, nowMs: number): FiscalPackage {
  const forwarded = state.forwarded;
  const versions = forwarded
    ? state.reportVersions.filter((v) => forwarded.versionIds.includes(v.id))
    : [];
  const stale = forwarded !== null && !isForwardedCurrent(state);
  return {
    project_id: PERIOD.project_id,
    period_id: PERIOD.id,
    available: forwarded !== null,
    forwarded_at: forwarded?.at ?? null,
    report_versions: versions.map((v) => ({
      id: v.id,
      report_id: v.report_id,
      author_name: personName(v.author_id),
      version: v.version,
    })),
    stale,
    stale_reason: stale
      ? "Há versão mais nova de relatório desde o encaminhamento. O gerente precisa reencaminhar."
      : null,
    expenses: state.expenses,
    findings: state.findings,
    decisions: state.decisions,
    open_requests: state.requests.filter((r) => r.status !== "resolved"),
    evidence: state.evidence,
    last_run: lastRun(state, "reanalysis", nowMs),
  };
}
