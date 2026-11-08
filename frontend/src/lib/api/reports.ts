/**
 * Validação de runtime das respostas reais de `/api/v1/reports` (#39).
 *
 * Os tipos vêm de `schema.d.ts` (gerado do OpenAPI). Os schemas Zod abaixo cobrem só os
 * campos que a UI usa, e o `satisfies` garante em tempo de compilação que eles não
 * divergem do contrato gerado.
 */
import { z } from "zod";
import type { components } from "@/lib/api/schema";

type Schemas = components["schemas"];

const Uuid = z.uuid();
const Timestamp = z.iso.datetime({ offset: true });

export const ClaimSectionSchema = z.enum(["technological_challenge", "hypothesis", "method", "result", "uncertainty"]);
export const ReviewStateApiSchema = z.enum(["text_approved", "changes_requested", "awaiting_review"]);

const ReportClaimSchema = z.object({
  section: ClaimSectionSchema,
  text: z.string(),
  status: z.enum(["supported", "pending", "disputed"]),
  evidence_ids: z.array(Uuid).default([]),
  question: z.string().nullable().optional(),
  ask_role: z.string().nullable().optional(),
  dispute_reason: z.string().nullable().optional(),
});

const MissingSchema = z.object({ field: z.string(), question: z.string(), ask_role: z.string() });

const ChangeSchema = z.object({
  reason: z.string(),
  operations: z.array(z.string()),
  affected_claim_ids: z.array(Uuid).default([]),
});

const DraftSchema = z.object({
  researcher_id: Uuid,
  project_id: Uuid,
  period: z.object({ start: z.iso.date(), end: z.iso.date(), timezone: z.string() }),
  summary: z.string(),
  claims: z.array(ReportClaimSchema),
  missing: z.array(MissingSchema).default([]),
  eligibility_note: z.string().optional(),
});

export const ApiReportVersionSchema = z
  .object({
    id: Uuid,
    number: z.number().int().positive(),
    draft: DraftSchema,
    claim_ids: z.array(Uuid),
    missing_ids: z.array(Uuid),
    supersedes_id: Uuid.nullable().optional(),
    change: ChangeSchema.nullable().optional(),
    created_at: Timestamp,
    is_synthetic: z.boolean().default(false),
  })
  // Os IDs são paralelos às listas do draft; resposta fora disso é inválida.
  .refine((v) => v.claim_ids.length === v.draft.claims.length && v.missing_ids.length === v.draft.missing.length, {
    message: "claim_ids/missing_ids não correspondem ao draft",
  });

const RoleReviewSchema = z.object({ state: ReviewStateApiSchema, review_id: Uuid.nullable() });

export const ApiReportVersionOutSchema = z.object({
  version: ApiReportVersionSchema,
  status: z.object({
    researcher_id: Uuid,
    current_version_id: Uuid,
    current_version_number: z.number().int().positive(),
    researcher: RoleReviewSchema,
    manager: RoleReviewSchema,
    approved_version_number: z.number().int().nullable(),
    approval_outdated: z.boolean(),
  }),
  is_current: z.boolean(),
  current_version_id: Uuid,
  reporting_period_id: Uuid,
});

export const ApiReviewOutSchema = z.object({
  review: z.object({
    id: Uuid,
    version_id: Uuid,
    reviewer_id: Uuid,
    reviewer_role: z.enum(["researcher", "manager"]),
    decision: z.enum(["text_approved", "changes_requested"]),
    comment: z.string().nullable().optional(),
    reviewed_at: Timestamp,
  }),
  new_version: ApiReportVersionSchema.nullable().optional(),
});

export type ApiReportVersion = z.infer<typeof ApiReportVersionSchema>;
export type ApiReportVersionOut = z.infer<typeof ApiReportVersionOutSchema>;
export type ApiReviewOut = z.infer<typeof ApiReviewOutSchema>;

// Garantia de compilação: o que a UI lê existe no contrato gerado com o mesmo tipo.
type Assignable<T, U extends T> = U;
export type ContractChecks = [
  Assignable<Pick<ApiReportVersionOut, "is_current" | "current_version_id">, Pick<Schemas["ReportVersionOut"], "is_current" | "current_version_id">>,
  Assignable<ApiReportVersion["number"], Schemas["ReportVersion"]["number"]>,
  Assignable<ApiReportVersion["draft"]["claims"][number]["section"], Schemas["ReportClaim"]["section"]>,
  Assignable<ApiReportVersion["draft"]["claims"][number]["status"], Schemas["ReportClaim"]["status"]>,
  Assignable<ApiReportVersionOut["status"]["researcher"]["state"], Schemas["RoleReview"]["state"]>,
  Assignable<ApiReviewOut["review"]["decision"], Schemas["ReportReview"]["decision"]>,
];
