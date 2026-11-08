"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";

import { periodQuery } from "@/components/basho/hooks";
import { EvidencePanel } from "@/components/basho/researcher/evidence-panel";
import { ReportBuilder } from "@/components/basho/researcher/report-builder";
import { ReportView } from "@/components/basho/researcher/report-view";
import { useReports } from "@/components/basho/reports-query";
import { RequirePersona, Shell } from "@/components/basho/shell";
import { Empty, ErrorBox, Loading } from "@/components/basho/ui";
import { ApiError, api } from "@/lib/api";
import type { DemoContext, ReportVersionOut } from "@/lib/types";

function AutoDraft({ ctx, userId }: { ctx: DemoContext; userId: string }) {
  const queryClient = useQueryClient();
  const [manual, setManual] = useState(false);
  const draft = useMutation({
    mutationFn: () => api.post<ReportVersionOut>(`projects/${ctx.project_id}/reports/auto-draft?${periodQuery(ctx)}`, {}),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ["reports"] }),
  });
  const { mutate, isIdle } = draft;
  useEffect(() => { if (isIdle) mutate(); }, [isIdle, mutate]);
  if (draft.isPending) return <Loading label="Preparando o rascunho do seu relatório a partir das evidências…" />;
  if (draft.isError) {
    const noEvidence = draft.error instanceof ApiError && draft.error.status === 404;
    return (
      <div className="space-y-3">
        {noEvidence ? <Empty>Ainda não há evidências suas no período para preparar o relatório.</Empty> : <ErrorBox error={draft.error} onRetry={() => draft.reset()} />}
        <button type="button" className="text-xs text-zinc-500 underline-offset-2 hover:underline" onClick={() => setManual(!manual)}>
          {manual ? "fechar" : "montar o relatório manualmente"}
        </button>
        {manual && <ReportBuilder ctx={ctx} researcherId={userId} />}
      </div>
    );
  }
  return <Loading label="Abrindo o rascunho…" />;
}

function ResearcherWork({ ctx, userId }: { ctx: DemoContext; userId: string }) {
  const reports = useReports(ctx);
  const mine = reports.data?.find((r) => r.status.researcher_id === userId);
  return (
    <div className="space-y-6">
      {reports.isPending && <Loading />}
      {reports.isError && <ErrorBox error={reports.error} onRetry={() => void reports.refetch()} />}
      {reports.data && (mine ? <ReportView key={mine.status.researcher_id} ctx={ctx} current={mine} canAct /> : <AutoDraft ctx={ctx} userId={userId} />)}
      <EvidencePanel ctx={ctx} userId={userId} />
    </div>
  );
}

export default function ResearcherPage() {
  return (
    <Shell>
      {(ctx, persona) => (
        <>
          <h1 className="mb-4 text-2xl font-semibold">Pesquisador</h1>
          <RequirePersona persona={persona} role="researcher" ctx={ctx}>
            {persona && <ResearcherWork ctx={ctx} userId={persona.userId} />}
          </RequirePersona>
        </>
      )}
    </Shell>
  );
}
