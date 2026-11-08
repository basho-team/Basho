/**
 * Contrato entre o navegador e o BFF (route handlers em `app/api/bff`).
 *
 * Este arquivo é seguro para o cliente: não lê variáveis de ambiente nem contém segredos.
 * A identidade é escolhida pela troca de papel da demonstração: o navegador envia só o papel
 * (`X-Demo-Role`) e, na revisão de relatório, o `reviewer_id`. O BFF só limita os pares
 * (pessoa, papel) a uma lista do servidor; ele NÃO autentica ninguém (placeholder até #47).
 * O segredo e os headers `X-Basho-*` que o backend exige nunca passam pelo navegador.
 */
import { z } from "zod";

export const BFF_BASE = "/api/bff";

/** Papel da demonstração que o navegador declara ao BFF (nunca é um header `X-Basho-*`). */
export const DEMO_ROLE_HEADER = "X-Demo-Role";

const seg = encodeURIComponent;

export const bffPaths = {
  report: (versionId: string) => `${BFF_BASE}/reports/${seg(versionId)}`,
  review: (versionId: string) => `${BFF_BASE}/reports/${seg(versionId)}/review`,
  project: (projectId: string) => `${BFF_BASE}/projects/${seg(projectId)}`,
  pending: (projectId: string, query: PendingQuery) => {
    const params = new URLSearchParams({ limit: String(query.limit), offset: String(query.offset) });
    if (query.status) params.set("status", query.status);
    return `${BFF_BASE}/projects/${seg(projectId)}/pending?${params.toString()}`;
  },
  dossier: (projectId: string) => `${BFF_BASE}/projects/${seg(projectId)}/dossier`,
  answer: (pendingId: string) => `${BFF_BASE}/pending/${seg(pendingId)}/answer`,
  approval: (artifactId: string) => `${BFF_BASE}/artifacts/${seg(artifactId)}/approval`,
};

/** Códigos de erro que o BFF devolve no envelope `ApiError`. */
export const BffErrorCode = {
  invalidRequest: "INVALID_REQUEST",
  notFound: "NOT_FOUND",
  forbidden: "FORBIDDEN",
  versionConflict: "VERSION_CONFLICT",
  stateConflict: "STATE_CONFLICT",
  reviewUnavailable: "REVIEW_UNAVAILABLE",
  identityUnavailable: "IDENTITY_UNAVAILABLE",
  invalidReview: "INVALID_REVIEW",
  invalidAnswer: "INVALID_ANSWER",
  tooLarge: "TOO_LARGE",
  backendUnavailable: "BACKEND_UNAVAILABLE",
  invalidResponse: "INVALID_RESPONSE",
  serverConfig: "SERVER_CONFIG",
} as const;

export const ReviewerRoleSchema = z.enum(["researcher", "manager"]);
export type ReviewerRole = z.infer<typeof ReviewerRoleSchema>;

const ReviseClaimOpSchema = z.strictObject({
  kind: z.literal("revise_claim"),
  claim_id: z.uuid(),
  text: z.string().min(1),
  status: z.enum(["supported", "pending", "disputed"]),
  evidence_ids: z.array(z.uuid()),
  question: z.string().nullable().optional(),
  ask_role: z.string().nullable().optional(),
  dispute_reason: z.string().nullable().optional(),
});

/**
 * Corpo aceito pelo BFF em `POST /reports/{id}/review`. Só a operação que a UI usa
 * (`revise_claim`) é aceita; o resto do contrato do backend fica fechado aqui.
 */
export const BffReviewRequestSchema = z.strictObject({
  reviewer_id: z.uuid(),
  role: ReviewerRoleSchema,
  decision: z.enum(["text_approved", "changes_requested"]),
  comment: z.string().trim().min(1).nullable().optional(),
  correction: z
    .strictObject({
      reason: z.string().trim().min(10),
      operations: z.array(ReviseClaimOpSchema).min(1).max(20),
    })
    .nullable()
    .optional(),
});
export type BffReviewRequest = z.infer<typeof BffReviewRequestSchema>;

/** Limites do backend (`PendingAnswerIn.answer`, `MAX_PAGE_SIZE`). */
export const MAX_ANSWER_LENGTH = 4000;
export const MAX_PENDING_PAGE = 200;

/** `POST /pending/{id}/answer`: só texto. `corrected_payload` fica fechado até a UI usar. */
export const BffAnswerRequestSchema = z.strictObject({
  answer: z.string().trim().min(1).max(MAX_ANSWER_LENGTH),
});
export type BffAnswerRequest = z.infer<typeof BffAnswerRequestSchema>;

/** `POST /artifacts/{id}/approval` (formal, só gerente). */
export const BffApprovalRequestSchema = z.strictObject({
  decision: z.enum(["approve", "reject"]),
  comment: z.string().trim().min(1).max(MAX_ANSWER_LENGTH).nullable().optional(),
});
export type BffApprovalRequest = z.infer<typeof BffApprovalRequestSchema>;

export const PendingQuerySchema = z.object({
  status: z.enum(["open", "answered", "resolved"]).optional(),
  limit: z.coerce.number().int().min(1).max(MAX_PENDING_PAGE).default(50),
  offset: z.coerce.number().int().min(0).default(0),
});
export type PendingQuery = z.infer<typeof PendingQuerySchema>;
