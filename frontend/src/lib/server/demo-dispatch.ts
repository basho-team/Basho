import "server-only";
import { z } from "zod";
import type { DemoUser, AppRole } from "@/lib/auth/shared";
import { RoleSchema } from "@/lib/auth/shared";
import { createMockSource } from "@/lib/data/mock-source";
import type { DataSource } from "@/lib/data/source";
import { DataSourceError } from "@/lib/data/source";

const Id = z.string().min(1).max(150);
const Note = z.string().trim().min(3).max(4000);
const Review = z.object({ reportVersionId: Id, reviewerId: Id, role: RoleSchema,
  decision: z.enum(["approve", "request_changes"]), justification: Note }).strict();
const Correction = z.object({ reportVersionId: Id, reviewerId: Id, role: RoleSchema,
  claimId: Id, newText: Note, justification: Note }).strict();

export const DemoRequestSchema = z.discriminatedUnion("operation", [
  z.object({ operation: z.literal("getContext"), args: z.tuple([]) }).strict(),
  z.object({ operation: z.literal("listReports"), args: z.tuple([Id]) }).strict(),
  z.object({ operation: z.literal("getReport"), args: z.tuple([Id, z.number().int().positive().nullable()]) }).strict(),
  z.object({ operation: z.literal("submitReview"), args: z.tuple([Review]) }).strict(),
  z.object({ operation: z.literal("submitCorrection"), args: z.tuple([Correction]) }).strict(),
  z.object({ operation: z.literal("getConsolidation"), args: z.tuple([Id]) }).strict(),
  z.object({ operation: z.literal("requestClarification"), args: z.tuple([z.object({ reportId: Id, question: Note }).strict()]) }).strict(),
  z.object({ operation: z.literal("triggerClosing"), args: z.tuple([Id]) }).strict(),
  z.object({ operation: z.literal("getRun"), args: z.tuple([Id]) }).strict(),
  z.object({ operation: z.literal("forwardToFiscal"), args: z.tuple([Id]) }).strict(),
  z.object({ operation: z.literal("getFiscalPackage"), args: z.tuple([Id]) }).strict(),
  z.object({ operation: z.literal("recordFiscalDecision"), args: z.tuple([z.object({
    findingId: Id, decidedBy: Id, decision: z.enum(["agree", "disagree", "defer"]), note: Note,
  }).strict()]) }).strict(),
  z.object({ operation: z.literal("returnPending"), args: z.tuple([z.object({
    findingId: Id, assigneeRole: z.enum(["researcher", "manager"]), reason: Note, evidenceNeeded: Note,
  }).strict()]) }).strict(),
  z.object({ operation: z.literal("listPendingFor"), args: z.tuple([RoleSchema, Id.nullable()]) }).strict(),
  z.object({ operation: z.literal("respondPending"), args: z.tuple([z.object({
    requestId: Id, respondedBy: Id, response: Note,
  }).strict()]) }).strict(),
  z.object({ operation: z.literal("decideArtifact"), args: z.tuple([z.object({
    artifactId: Id, decision: z.enum(["approve", "reject"]), comment: z.string().max(4000).nullable(),
  }).strict()]) }).strict(),
  z.object({ operation: z.literal("getDossier"), args: z.tuple([]) }).strict(),
]);

function denied(): never {
  throw new DataSourceError({ code: "FORBIDDEN", message: "Sua função não permite esta operação.", retryable: false, correlation_id: "demo-local" });
}

function allow(user: DemoUser, ...roles: AppRole[]) {
  if (user.organizationId !== "org-lumen" || !roles.includes(user.role)) denied();
}

async function ownVersion(source: DataSource, user: DemoUser, versionId: string) {
  allow(user, "researcher");
  const reports = await source.listReports("per-2026-10");
  for (const report of reports.filter(item => item.author_id === user.personId)) {
    const detail = await source.getReport(report.report_id);
    if (detail.history.some(version => version.id === versionId)) return;
  }
  denied();
}

/** A mesma organização sintética é compartilhada pelas contas, apenas neste processo local. */
const demoGlobal = globalThis as typeof globalThis & { bashoDemoWorkspace?: DataSource };
export function demoWorkspace(): DataSource {
  return demoGlobal.bashoDemoWorkspace ??= createMockSource({ latencyMs: 0, failures: () => [] });
}

export async function dispatchDemo(user: DemoUser, data: z.infer<typeof DemoRequestSchema>, source: DataSource): Promise<unknown> {
  switch (data.operation) {
    case "getContext": return source.getContext();
    case "listReports": {
      allow(user, "researcher", "manager");
      const reports = await source.listReports(data.args[0]);
      return user.role === "researcher" ? reports.filter(item => item.author_id === user.personId) : reports;
    }
    case "getReport": {
      allow(user, "researcher", "manager");
      const detail = await source.getReport(data.args[0], data.args[1] ?? undefined);
      if (user.role === "researcher" && detail.version.author_id !== user.personId) denied();
      return detail;
    }
    case "submitReview":
    case "submitCorrection": {
      const input = data.args[0];
      if (input.role !== user.role || input.reviewerId !== user.personId) denied();
      await ownVersion(source, user, input.reportVersionId);
      return data.operation === "submitReview" ? source.submitReview(data.args[0]) : source.submitCorrection(data.args[0]);
    }
    case "listPendingFor":
      if (data.args[0] !== user.role || (data.args[1] !== null && data.args[1] !== user.personId)) denied();
      return source.listPendingFor(user.role, user.personId);
    case "respondPending": {
      if (data.args[0].respondedBy !== user.personId) denied();
      const pending = await source.listPendingFor(user.role, user.personId);
      if (!pending.some(item => item.id === data.args[0].requestId)) denied();
      return source.respondPending(data.args[0]);
    }
    case "decideArtifact": allow(user, "manager"); return source.decideArtifact(data.args[0]);
    case "getDossier": allow(user, "manager", "fiscal"); return source.getDossier();
    default: return dispatchManagement(user, data, source);
  }
}

type ManagementRequest = Extract<z.infer<typeof DemoRequestSchema>, { operation:
  "getConsolidation" | "requestClarification" | "triggerClosing" | "getRun" |
  "forwardToFiscal" | "getFiscalPackage" | "recordFiscalDecision" | "returnPending" }>;

function dispatchManagement(user: DemoUser, data: ManagementRequest, source: DataSource): Promise<unknown> {
  switch (data.operation) {
    case "getConsolidation": allow(user, "manager"); return source.getConsolidation(data.args[0]);
    case "requestClarification": allow(user, "manager"); return source.requestClarification(data.args[0]);
    case "triggerClosing": allow(user, "manager"); return source.triggerClosing(data.args[0]);
    case "getRun": allow(user, "manager", "fiscal"); return source.getRun(data.args[0]);
    case "forwardToFiscal": allow(user, "manager"); return source.forwardToFiscal(data.args[0]);
    case "getFiscalPackage": allow(user, "fiscal"); return source.getFiscalPackage(data.args[0]);
    case "recordFiscalDecision": {
      allow(user, "fiscal");
      if (data.args[0].decidedBy !== user.personId) denied();
      return source.recordFiscalDecision(data.args[0]);
    }
    case "returnPending": allow(user, "fiscal"); return source.returnPending(data.args[0]);
    default: return data satisfies never;
  }
}
