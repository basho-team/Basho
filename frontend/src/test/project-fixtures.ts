/** Respostas sintéticas no formato real de projetos/pendências/dossiê (#5), só para testes. */
import { mockDossier } from "@/lib/data/mock-dossier";
import { MANAGER_ID } from "@/test/api-fixtures";

export const PROJECT_ID = "00000000-0000-4000-8000-000000000001";
export const PENDING_OPEN_ID = "77777777-0000-4000-8000-000000000001";
export const PENDING_APPROVAL_ID = "77777777-0000-4000-8000-000000000002";
export const ARTIFACT_ID = "88888888-0000-4000-8000-000000000001";

type Kind = "missing_justification" | "approval_required" | "checker_disagreement";

export function pendingItem(id: string, options: { kind?: Kind; assignee?: string; status?: "open" | "answered" | "resolved" } = {}) {
  return {
    id,
    project_id: PROJECT_ID,
    activity_id: null,
    kind: options.kind ?? "missing_justification",
    title: "Registro de atividade: integração da bancada B",
    question: "Quantas horas formais foram declaradas para esta atividade?",
    assignee_role: options.assignee ?? "researcher",
    artifact_id: ARTIFACT_ID,
    artifact_status: "needs_human",
    verification_event_id: "66666666-0000-4000-8000-000000000001",
    status: options.status ?? "open",
    resolved: (options.status ?? "open") !== "open",
    response: null,
    created_at: "2026-11-08T10:00:00Z",
  };
}

export function approvalOut(decision: "approve" | "reject" = "approve") {
  return {
    artifact_id: ARTIFACT_ID,
    decision,
    status: decision === "approve" ? "approved" : "rejected",
    approver_id: MANAGER_ID,
    comment: null,
    evidence_event_id: "55555555-0000-4000-8000-000000000001",
    created_at: "2026-11-08T11:00:00Z",
  };
}

export const dossierOut = () => mockDossier();
