/**
 * Fonte de dados real. As rotas dependem da ratificação dos contratos pelo Vitor;
 * até lá, cada operação falha de forma explícita em vez de fingir dados.
 */
import { DataSourceError, type DataSource } from "@/lib/data/source";

function notImplemented(operation: string): Promise<never> {
  return Promise.reject(
    new DataSourceError({
      code: "NOT_IMPLEMENTED",
      message: `A operação "${operation}" ainda não existe na API. Use NEXT_PUBLIC_DATA_SOURCE=mock para a demonstração.`,
      correlation_id: `ui-${Date.now()}`,
      retryable: false,
    }),
  );
}

export function createApiSource(): DataSource {
  return {
    kind: "api",
    getContext: () => notImplemented("getContext"),
    listReports: () => notImplemented("listReports"),
    getReport: () => notImplemented("getReport"),
    submitReview: () => notImplemented("submitReview"),
    submitCorrection: () => notImplemented("submitCorrection"),
    getConsolidation: () => notImplemented("getConsolidation"),
    requestClarification: () => notImplemented("requestClarification"),
    triggerClosing: () => notImplemented("triggerClosing"),
    getRun: () => notImplemented("getRun"),
    forwardToFiscal: () => notImplemented("forwardToFiscal"),
    getFiscalPackage: () => notImplemented("getFiscalPackage"),
    recordFiscalDecision: () => notImplemented("recordFiscalDecision"),
    returnPending: () => notImplemented("returnPending"),
    listPendingFor: () => notImplemented("listPendingFor"),
    respondPending: () => notImplemented("respondPending"),
  };
}
