/**
 * Contrato entre o navegador e o BFF (route handlers em `app/api/bff`).
 *
 * Este arquivo é seguro para o cliente: não lê variáveis de ambiente nem contém segredos.
 * A identidade do revisor é escolhida pela troca de papel da demonstração e conferida pelo
 * BFF contra uma lista de revisores configurada no servidor; o segredo que o backend exige
 * nunca passa pelo navegador.
 */
import { z } from "zod";

export const BFF_BASE = "/api/bff";

export const bffPaths = {
  report: (versionId: string) => `${BFF_BASE}/reports/${encodeURIComponent(versionId)}`,
  review: (versionId: string) => `${BFF_BASE}/reports/${encodeURIComponent(versionId)}/review`,
};

/** Códigos de erro que o BFF devolve no envelope `ApiError`. */
export const BffErrorCode = {
  invalidRequest: "INVALID_REQUEST",
  notFound: "NOT_FOUND",
  forbidden: "FORBIDDEN",
  versionConflict: "VERSION_CONFLICT",
  reviewUnavailable: "REVIEW_UNAVAILABLE",
  invalidReview: "INVALID_REVIEW",
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

/** Corpo extra de um 409: a versão atual para a UI recarregar. */
export const VersionConflictDetailSchema = z.object({
  current_version_id: z.uuid(),
});
