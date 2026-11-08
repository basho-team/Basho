/** Respostas sintéticas no formato real de `/api/v1/reports` (#39), só para testes. */
import type { ApiReportVersionOut } from "@/lib/api/reports";

export const RESEARCHER_ID = "11111111-1111-4111-8111-111111111111";
export const MANAGER_ID = "22222222-2222-4222-8222-222222222222";
export const V1_ID = "aaaaaaaa-0000-4000-8000-000000000001";
export const V2_ID = "aaaaaaaa-0000-4000-8000-000000000002";
export const CLAIM_ID = "cccccccc-0000-4000-8000-000000000001";
export const PENDING_CLAIM_ID = "cccccccc-0000-4000-8000-000000000002";
export const MISSING_ID = "dddddddd-0000-4000-8000-000000000001";
export const EVIDENCE_ID = "eeeeeeee-0000-4000-8000-000000000001";
const PERIOD_ID = "ffffffff-0000-4000-8000-000000000001";
const PROJECT_ID = "99999999-0000-4000-8000-000000000001";

type RoleState = "text_approved" | "changes_requested" | "awaiting_review";

interface VersionOptions {
  id: string;
  number: number;
  supersedesId: string | null;
  currentId: string;
  currentNumber: number;
  researcher?: RoleState;
  manager?: RoleState;
}

export function versionOut(options: VersionOptions): ApiReportVersionOut {
  const researcher = options.researcher ?? "awaiting_review";
  const manager = options.manager ?? "awaiting_review";
  return {
    version: {
      id: options.id,
      number: options.number,
      draft: {
        researcher_id: RESEARCHER_ID,
        project_id: PROJECT_ID,
        period: { start: "2026-10-01", end: "2026-10-31", timezone: "America/Sao_Paulo" },
        summary: "Resumo sintético do período para testes.",
        claims: [
          {
            section: "method",
            text: "Integrou a coleta da bancada B ao pipeline.",
            status: "supported",
            evidence_ids: [EVIDENCE_ID],
          },
          {
            section: "result",
            text: "Resultado da calibração ainda sem fonte.",
            status: "pending",
            evidence_ids: [],
            question: "Qual foi o erro medido na calibração?",
            ask_role: "pesquisador",
          },
        ],
        missing: [{ field: "formal_hours", question: "Quantas horas formais foram declaradas?", ask_role: "pesquisador" }],
      },
      claim_ids: [CLAIM_ID, PENDING_CLAIM_ID],
      missing_ids: [MISSING_ID],
      supersedes_id: options.supersedesId,
      change: options.supersedesId
        ? { reason: "Faltou a bancada C no texto.", operations: ["revise_claim"], affected_claim_ids: [CLAIM_ID] }
        : null,
      created_at: `2026-11-0${options.number}T12:00:00Z`,
      is_synthetic: true,
    },
    status: {
      researcher_id: RESEARCHER_ID,
      current_version_id: options.currentId,
      current_version_number: options.currentNumber,
      researcher: { state: researcher, review_id: researcher === "awaiting_review" ? null : "bbbbbbbb-0000-4000-8000-000000000001" },
      manager: { state: manager, review_id: manager === "awaiting_review" ? null : "bbbbbbbb-0000-4000-8000-000000000002" },
      approved_version_number: null,
      approval_outdated: false,
    },
    is_current: options.id === options.currentId,
    current_version_id: options.currentId,
    reporting_period_id: PERIOD_ID,
  };
}

/** Série de duas versões: v1 substituída pela v2 (atual). */
export function twoVersionSeries(): Record<string, ApiReportVersionOut> {
  return {
    [V1_ID]: versionOut({ id: V1_ID, number: 1, supersedesId: null, currentId: V2_ID, currentNumber: 2 }),
    [V2_ID]: versionOut({ id: V2_ID, number: 2, supersedesId: V1_ID, currentId: V2_ID, currentNumber: 2 }),
  };
}

export function reviewOut(versionId: string, decision: "text_approved" | "changes_requested") {
  return {
    review: {
      id: "bbbbbbbb-0000-4000-8000-000000000009",
      version_id: versionId,
      reviewer_id: RESEARCHER_ID,
      reviewer_role: "researcher",
      decision,
      comment: "Confere com o diário.",
      reviewed_at: "2026-11-08T10:00:00Z",
    },
    evidence_event_id: "bbbbbbbb-0000-4000-8000-00000000000a",
    new_version: null,
  };
}

export function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}
