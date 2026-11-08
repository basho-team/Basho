"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { Role, Run } from "@/lib/contracts/provisional";
import { dataSource, DataSourceError } from "@/lib/data";
import type {
  ClarificationInput,
  CorrectionInput,
  FiscalDecisionInput,
  RespondPendingInput,
  ReturnPendingInput,
  ReviewInput,
} from "@/lib/data/source";

const ACTIVE_RUN_POLL_MS = 700;

export const queryKeys = {
  all: ["basho"] as const,
  context: () => [...queryKeys.all, "context"] as const,
  reports: (periodId: string) => [...queryKeys.all, "reports", periodId] as const,
  report: (reportId: string, version?: number) =>
    [...queryKeys.all, "report", reportId, version ?? "latest"] as const,
  consolidation: (periodId: string) => [...queryKeys.all, "consolidation", periodId] as const,
  fiscalPackage: (periodId: string) => [...queryKeys.all, "fiscal", periodId] as const,
  pending: (role: Role, personId?: string) => [...queryKeys.all, "pending", role, personId ?? "all"] as const,
  run: (runId: string) => [...queryKeys.all, "run", runId] as const,
};

export function isRunActive(run: Run | null | undefined): boolean {
  return run?.status === "queued" || run?.status === "running";
}

const pollWhileActive = (run: Run | null | undefined) => (isRunActive(run) ? ACTIVE_RUN_POLL_MS : false);

export function useProjectContext() {
  return useQuery({ queryKey: queryKeys.context(), queryFn: () => dataSource.getContext() });
}

export function useReports(periodId: string | undefined) {
  return useQuery({
    queryKey: queryKeys.reports(periodId ?? ""),
    queryFn: () => dataSource.listReports(periodId ?? ""),
    enabled: Boolean(periodId),
  });
}

export function useReport(reportId: string, version?: number) {
  return useQuery({
    queryKey: queryKeys.report(reportId, version),
    queryFn: () => dataSource.getReport(reportId, version),
  });
}

export function useConsolidation(periodId: string | undefined) {
  return useQuery({
    queryKey: queryKeys.consolidation(periodId ?? ""),
    queryFn: () => dataSource.getConsolidation(periodId ?? ""),
    enabled: Boolean(periodId),
    refetchInterval: (query) => pollWhileActive(query.state.data?.last_run),
  });
}

export function useFiscalPackage(periodId: string | undefined) {
  return useQuery({
    queryKey: queryKeys.fiscalPackage(periodId ?? ""),
    queryFn: () => dataSource.getFiscalPackage(periodId ?? ""),
    enabled: Boolean(periodId),
    refetchInterval: (query) => pollWhileActive(query.state.data?.last_run),
  });
}

export function usePendingFor(role: Role, personId?: string) {
  return useQuery({
    queryKey: queryKeys.pending(role, personId),
    queryFn: () => dataSource.listPendingFor(role, personId),
    refetchInterval: ACTIVE_RUN_POLL_MS * 4,
  });
}

/** A versão revisada deixou de ser a atual (409 da API ou do mock). */
export function isVersionConflict(error: unknown): boolean {
  return error instanceof DataSourceError && error.error.code === "VERSION_CONFLICT";
}

/**
 * Toda escrita pode afetar várias telas: invalida tudo do domínio. Num conflito de versão,
 * recarrega também, para a tela mostrar a versão nova.
 */
function useDomainMutation<TInput, TOutput>(fn: (input: TInput) => Promise<TOutput>) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: fn,
    onSuccess: () => client.invalidateQueries({ queryKey: queryKeys.all }),
    onError: (error) => {
      if (isVersionConflict(error)) void client.invalidateQueries({ queryKey: queryKeys.all });
    },
  });
}

export const useSubmitReview = () => useDomainMutation((i: ReviewInput) => dataSource.submitReview(i));
export const useSubmitCorrection = () =>
  useDomainMutation((i: CorrectionInput) => dataSource.submitCorrection(i));
export const useRequestClarification = () =>
  useDomainMutation((i: ClarificationInput) => dataSource.requestClarification(i));
export const useTriggerClosing = () => useDomainMutation((periodId: string) => dataSource.triggerClosing(periodId));
export const useForwardToFiscal = () =>
  useDomainMutation((periodId: string) => dataSource.forwardToFiscal(periodId));
export const useRecordFiscalDecision = () =>
  useDomainMutation((i: FiscalDecisionInput) => dataSource.recordFiscalDecision(i));
export const useReturnPending = () => useDomainMutation((i: ReturnPendingInput) => dataSource.returnPending(i));
export const useRespondPending = () =>
  useDomainMutation((i: RespondPendingInput) => dataSource.respondPending(i));
