/**
 * Validação de runtime das respostas de projetos, pendências, aprovação e dossiê (#5, PR #54).
 *
 * Os tipos vêm de `schema.d.ts` (gerado do OpenAPI). Os schemas Zod cobrem o que a UI usa e
 * descartam o resto. O dossiê e as pendências são consumidos neste formato pela UI, sem
 * camada provisória: não declare formatos paralelos em componentes.
 */
import { z } from "zod";
import type { components } from "@/lib/api/schema";

type Schemas = components["schemas"];

const Uuid = z.uuid();
const Timestamp = z.iso.datetime({ offset: true });
const JsonObject = z.record(z.string(), z.unknown());

export const ArtifactStatusSchema = z.enum(["draft", "proposed", "verified", "needs_human", "approved", "rejected", "needs_review"]);
export const PendingKindSchema = z.enum([
  "missing_justification",
  "missing_activity_record",
  "checker_disagreement",
  "approval_required",
  "tool_failure",
  "needs_review",
]);
export const PendingStatusSchema = z.enum(["open", "answered", "resolved"]);

const ActivitySchema = z.object({
  id: Uuid,
  title: z.string(),
  description: z.string().nullable(),
  is_synthetic: z.boolean(),
});

export const ProjectSchema = z.object({
  id: Uuid,
  name: z.string(),
  description: z.string().nullable(),
  is_synthetic: z.boolean(),
  created_at: Timestamp,
  activities: z.array(ActivitySchema),
  open_pending: z.number().int().nonnegative(),
});

export const PendingItemSchema = z.object({
  id: Uuid,
  project_id: Uuid,
  activity_id: Uuid.nullable(),
  kind: PendingKindSchema,
  title: z.string(),
  question: z.string(),
  assignee_role: z.string(),
  artifact_id: Uuid.nullable(),
  artifact_status: ArtifactStatusSchema.nullable(),
  status: PendingStatusSchema,
  response: z.string().nullable(),
  created_at: Timestamp,
});

export const PendingPageSchema = z.object({
  items: z.array(PendingItemSchema),
  next_offset: z.number().int().nonnegative().nullable(),
});

export const PendingAnswerOutSchema = z.object({ pending: PendingItemSchema, correction_event_id: Uuid });

export const ApprovalSchema = z.object({
  artifact_id: Uuid,
  decision: z.enum(["approve", "reject"]),
  status: ArtifactStatusSchema,
  approver_id: Uuid,
  comment: z.string().nullable(),
  evidence_event_id: Uuid,
  created_at: Timestamp,
});

export const EvidenceEventSchema = z.object({
  id: Uuid,
  kind: z.string(),
  source: z.string(),
  source_ref: z.string().nullable().optional(),
  actor: z.object({ type: z.string(), id: z.string(), model: z.string().nullable().optional() }),
  payload: JsonObject,
  supersedes: Uuid.nullable().optional(),
  is_synthetic: z.boolean().default(false),
  content_hash: z.string(),
  created_at: Timestamp,
});

const VerificationSchema = z.object({
  verdict: z.enum(["pass", "fail"]),
  checker: z.string(),
  issues: z.array(z.object({ code: z.string(), message: z.string(), severity: z.string() })).default([]),
  unsupported_claims: z.array(z.object({ claim_text: z.string(), reason: z.string() })).default([]),
});

const RunMetricsSchema = z.object({
  run_id: z.string(),
  model: z.string(),
  input_tokens: z.number().int(),
  output_tokens: z.number().int(),
  latency_ms: z.number().int(),
  cost_usd: z.number(),
});

export const DossierEntrySchema = z.object({
  artifact_id: Uuid,
  activity_id: Uuid.nullable(),
  title: z.string(),
  status: ArtifactStatusSchema,
  content: JsonObject,
  evidence: z.array(EvidenceEventSchema),
  verifications: z.array(VerificationSchema),
  history: z.array(EvidenceEventSchema),
  approval: ApprovalSchema.nullable(),
  runs: z.array(RunMetricsSchema).default([]),
});

export const DossierSchema = z.object({ project: ProjectSchema, entries: z.array(DossierEntrySchema) });

/** 409 de pendência/aprovação (`ConflictOut`). O BFF repassa só `code` e `current_status`. */
export const ConflictSchema = z.object({ code: z.string().min(1), current_status: z.string().nullable().optional() });

export type ArtifactStatus = z.infer<typeof ArtifactStatusSchema>;
export type PendingKind = z.infer<typeof PendingKindSchema>;
export type ApiProject = z.infer<typeof ProjectSchema>;
export type ApiPendingItem = z.infer<typeof PendingItemSchema>;
export type ArtifactApproval = z.infer<typeof ApprovalSchema>;
export type EvidenceEvent = z.infer<typeof EvidenceEventSchema>;
export type DossierEntry = z.infer<typeof DossierEntrySchema>;
export type Dossier = z.infer<typeof DossierSchema>;

// Garantia de compilação: enums e campos lidos existem no contrato gerado.
type Assignable<T, U extends T> = U;
export type ContractChecks = [
  Assignable<ArtifactStatus, Schemas["ArtifactStatus"]>,
  Assignable<PendingKind, Schemas["PendingKind"]>,
  Assignable<ApiPendingItem["status"], Schemas["PendingItemOut"]["status"]>,
  Assignable<ArtifactApproval["decision"], Schemas["ApprovalOut"]["decision"]>,
  Assignable<Pick<ApiProject, "open_pending">, Pick<Schemas["ProjectOut"], "open_pending">>,
  Assignable<Pick<Dossier["entries"][number], "artifact_id" | "title">, Pick<Schemas["DossierEntryOut"], "artifact_id" | "title">>,
];
