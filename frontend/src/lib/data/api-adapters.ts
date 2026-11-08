/**
 * Tradução do contrato real (`/api/v1/reports`, #39) para os tipos da UI.
 *
 * É só mapeamento de formato: estados, aprovações e versão atual vêm prontos do backend.
 * O que a API ainda não expõe (conteúdo das evidências, justificativa por afirmação,
 * comentário e data da revisão) fica vazio ou `null`. A UI nunca preenche nada disso.
 */
import type { ApiReportVersion, ApiReportVersionOut, ApiReviewOut } from "@/lib/api/reports";
import type { Claim, Gap, ReportDetail, ReportVersion, Review, ReviewState } from "@/lib/contracts/provisional";

function formatIsoDate(iso: string): string {
  const [year, month, day] = iso.split("-");
  return `${day}/${month}/${year}`;
}

export function periodLabel(version: ApiReportVersion): string {
  const { start, end } = version.draft.period;
  return `${formatIsoDate(start)} a ${formatIsoDate(end)}`;
}

/** Estado exibido. A ordem dos papéis é a mesma do fluxo; quem decide cada estado é o backend. */
export function toReviewState(out: ApiReportVersionOut): ReviewState {
  if (!out.is_current) return "superseded";
  if (out.status.researcher.state !== "text_approved") return "awaiting_researcher";
  if (out.status.manager.state !== "text_approved") return "awaiting_manager";
  return "text_approved";
}

function claimJustification(claim: ApiReportVersion["draft"]["claims"][number]): string | null {
  if (claim.status === "pending") return claim.question ?? null;
  if (claim.status === "disputed") return claim.dispute_reason ?? null;
  return null;
}

function toClaims(version: ApiReportVersion): Claim[] {
  const corrected = new Set(version.change?.affected_claim_ids ?? []);
  return version.draft.claims.map((claim, index) => {
    const id = version.claim_ids[index];
    return {
      id,
      section: claim.section,
      text: claim.text,
      status: claim.status,
      evidence_ids: claim.evidence_ids,
      justification: claimJustification(claim),
      corrected_by_human: corrected.has(id),
    };
  });
}

function toGaps(version: ApiReportVersion): Gap[] {
  return version.draft.missing.map((missing, index) => ({
    id: version.missing_ids[index],
    claim_id: null,
    description: `Informação ausente: ${missing.field} (responsável: ${missing.ask_role})`,
    question: missing.question,
  }));
}

export function toReportVersion(out: ApiReportVersionOut, seriesKey: string): ReportVersion {
  const { version } = out;
  return {
    id: version.id,
    report_id: seriesKey,
    kind: "individual",
    project_id: version.draft.project_id,
    period_id: out.reporting_period_id,
    author_id: version.draft.researcher_id,
    version: version.number,
    created_at: version.created_at,
    review_state: toReviewState(out),
    claims: toClaims(version),
    gaps: toGaps(version),
    change_summary: version.change?.reason ?? null,
    stale: false,
    stale_reason: null,
  };
}

/** Revisões da versão atual, a partir do estado por papel que o backend devolve. */
function currentReviews(out: ApiReportVersionOut): Review[] {
  const { researcher, researcher_id } = out.status;
  if (!out.is_current || researcher.review_id === null || researcher.state === "awaiting_review") return [];
  return [
    {
      id: researcher.review_id,
      report_version_id: out.version.id,
      reviewer_id: researcher_id,
      role: "researcher",
      decision: researcher.state === "text_approved" ? "approve" : "request_changes",
      justification: null,
      created_at: null,
    },
  ];
}

/** `series` = todas as versões conhecidas da série; `selected` precisa estar nela. */
export function toReportDetail(seriesKey: string, series: ApiReportVersionOut[], selected: ApiReportVersionOut): ReportDetail {
  const ordered = [...series].sort((a, b) => a.version.number - b.version.number);
  return {
    version: toReportVersion(selected, seriesKey),
    period_label: periodLabel(selected.version),
    latest_version: selected.status.current_version_number,
    history: ordered.map((out) => ({ id: out.version.id, version: out.version.number, created_at: out.version.created_at })),
    reviews: currentReviews(selected),
    evidence: [],
  };
}

export function toReview(out: ApiReviewOut): Review {
  const { review } = out;
  return {
    id: review.id,
    report_version_id: review.version_id,
    reviewer_id: review.reviewer_id,
    role: review.reviewer_role,
    decision: review.decision === "text_approved" ? "approve" : "request_changes",
    justification: review.comment ?? null,
    created_at: review.reviewed_at,
  };
}
