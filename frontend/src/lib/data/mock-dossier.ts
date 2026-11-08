/**
 * SIMULAÇÃO: dossiê sintético no formato real (`DossierOut`, #5) para o modo demonstração.
 * Pessoas, repositório e números são fictícios e marcados `is_synthetic`.
 */
import type { Dossier, EvidenceEvent } from "@/lib/api/projects";

const PROJECT_ID = "00000000-0000-4000-8000-000000000001";
const ACTIVITY_ID = "00000000-0000-4000-8000-000000000011";
const ART_APPROVED = "00000000-0000-4000-8000-000000000101";
const ART_REVIEW = "00000000-0000-4000-8000-000000000102";
const ART_REVIEW_FIX = "00000000-0000-4000-8000-000000000103";
const EV_PR42 = "00000000-0000-4000-8000-000000000201";
const EV_COMMITS = "00000000-0000-4000-8000-000000000202";
const HASH = "0".repeat(63);

function event(id: string, partial: Omit<EvidenceEvent, "id" | "content_hash" | "is_synthetic">): EvidenceEvent {
  return { ...partial, id, content_hash: `${HASH}${id.slice(-1)}`, is_synthetic: true };
}

const pr42 = event(EV_PR42, {
  kind: "pull_request_observed",
  source: "github",
  source_ref: "lumen-demo/calibra#42",
  actor: { type: "system", id: "system" },
  payload: { title: "PR #42: experimento com filtro de Kalman adaptativo" },
  created_at: "2026-10-20T14:00:00Z",
});

const commits = event(EV_COMMITS, {
  kind: "commit_observed",
  source: "github",
  source_ref: "3e2a..9f10",
  actor: { type: "system", id: "system" },
  payload: { message: "coleta da bancada B integrada ao pipeline" },
  created_at: "2026-10-22T09:30:00Z",
});

export function mockDossier(): Dossier {
  return {
    project: {
      id: PROJECT_ID,
      name: "Calibra (demonstração)",
      description: "Projeto fictício para a demonstração do Basho.",
      is_synthetic: true,
      created_at: "2026-10-01T12:00:00Z",
      activities: [{ id: ACTIVITY_ID, title: "Calibração térmica adaptativa", description: null, is_synthetic: true }],
      open_pending: 1,
    },
    entries: [
      {
        artifact_id: ART_APPROVED,
        activity_id: ACTIVITY_ID,
        title: "Registro de atividade: filtro de Kalman adaptativo",
        status: "approved",
        content: { summary: "Experimento reduziu o erro médio no conjunto B, segundo o PR #42." },
        evidence: [pr42],
        verifications: [{ verdict: "pass", checker: "deterministic", issues: [], unsupported_claims: [] }],
        history: [
          event(ART_APPROVED, {
            kind: "activity_record",
            source: "agent",
            source_ref: null,
            actor: { type: "agent", id: "maker", model: "claude-opus-5-5" },
            payload: { artifact_type: "activity_record" },
            created_at: "2026-10-25T10:00:00Z",
          }),
        ],
        approval: {
          artifact_id: ART_APPROVED,
          decision: "approve",
          status: "approved",
          approver_id: "00000000-0000-4000-8000-000000000301",
          comment: "Confere com o PR.",
          evidence_event_id: "00000000-0000-4000-8000-000000000401",
          created_at: "2026-10-26T16:00:00Z",
        },
        runs: [
          { run_id: "run-demo-1", model: "claude-opus-5-5", input_tokens: 5200, output_tokens: 900, latency_ms: 8400, cost_usd: 0.11 },
        ],
      },
      {
        artifact_id: ART_REVIEW,
        activity_id: ACTIVITY_ID,
        title: "Registro de atividade: integração da bancada B",
        status: "needs_review",
        content: { summary: "Integração da coleta da bancada B ao pipeline." },
        evidence: [commits],
        verifications: [
          {
            verdict: "fail",
            checker: "checker-model",
            issues: [{ code: "uncited_claim", message: "Afirmação sobre a bancada C sem fonte.", severity: "error" }],
            unsupported_claims: [],
          },
        ],
        history: [
          event(ART_REVIEW, {
            kind: "activity_record",
            source: "agent",
            source_ref: null,
            actor: { type: "agent", id: "maker", model: "claude-opus-5-5" },
            payload: { artifact_type: "activity_record" },
            created_at: "2026-10-27T10:00:00Z",
          }),
          event(ART_REVIEW_FIX, {
            kind: "user_correction",
            source: "user",
            source_ref: null,
            actor: { type: "user", id: "pesquisador-demo" },
            payload: { answer: "A integração foi só na bancada B." },
            supersedes: ART_REVIEW,
            created_at: "2026-10-28T11:00:00Z",
          }),
        ],
        approval: null,
        runs: [],
      },
    ],
  };
}
