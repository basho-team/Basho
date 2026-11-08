import { z } from "zod";
import { DossierSchema, ApprovalSchema } from "@/lib/api/projects";
import { ConsolidationSchema, FiscalDecisionSchema, FiscalPackageSchema, PendingRequestSchema, PersonSchema,
  ProjectSchema, ReportDetailSchema, ReportingPeriodSchema, ReportSummarySchema, ReviewSchema, RunSchema } from "@/lib/contracts/provisional";
import type { DataSource } from "./source";
import { DataSourceError } from "./source";

export function createDemoSource(): DataSource {
  async function call<T>(operation: string, args: unknown[], schema: z.ZodType<T>): Promise<T> {
    let response: Response;
    try {
      response = await fetch("/api/demo", { method: "POST", cache: "no-store",
        headers: { "Content-Type": "application/json" }, body: JSON.stringify({ operation, args }) });
    } catch {
      throw new DataSourceError({ code: "UNAVAILABLE", message: "Não foi possível conectar ao servidor.", retryable: true, correlation_id: "demo-local" });
    }
    const body: unknown = await response.json();
    if (!response.ok) {
      const error = z.object({ code: z.string().optional(), message: z.string() }).safeParse(body);
      throw new DataSourceError({ code: error.success ? error.data.code ?? "FORBIDDEN" : "INVALID_RESPONSE",
        message: error.success ? error.data.message : "Resposta inválida.", retryable: false, correlation_id: "demo-local" });
    }
    const parsed = schema.safeParse(body);
    if (!parsed.success) throw new DataSourceError({ code: "INVALID_RESPONSE", message: "Resposta inválida do servidor.", retryable: false, correlation_id: "demo-local" });
    return parsed.data;
  }
  return {
    kind: "mock",
    getContext: () => call("getContext", [], z.object({ project: ProjectSchema, period: ReportingPeriodSchema, people: PersonSchema.array() })),
    listReports: period => call("listReports", [period], ReportSummarySchema.array()),
    getReport: (id, version) => call("getReport", [id, version ?? null], ReportDetailSchema),
    submitReview: input => call("submitReview", [input], ReviewSchema),
    submitCorrection: input => call("submitCorrection", [input], ReportDetailSchema),
    getConsolidation: period => call("getConsolidation", [period], ConsolidationSchema),
    requestClarification: input => call("requestClarification", [input], PendingRequestSchema),
    triggerClosing: period => call("triggerClosing", [period], RunSchema),
    getRun: id => call("getRun", [id], RunSchema),
    forwardToFiscal: period => call("forwardToFiscal", [period], ConsolidationSchema),
    getFiscalPackage: period => call("getFiscalPackage", [period], FiscalPackageSchema),
    recordFiscalDecision: input => call("recordFiscalDecision", [input], FiscalDecisionSchema),
    returnPending: input => call("returnPending", [input], PendingRequestSchema),
    listPendingFor: (role, personId) => call("listPendingFor", [role, personId ?? null], PendingRequestSchema.array()),
    respondPending: input => call("respondPending", [input], PendingRequestSchema),
    decideArtifact: input => call("decideArtifact", [input], ApprovalSchema),
    getDossier: () => call("getDossier", [], DossierSchema),
  };
}
