"use client";

import { EvidencePanel } from "@/components/basho/researcher/evidence-panel";
import { ReportBuilder } from "@/components/basho/researcher/report-builder";
import { ReportView } from "@/components/basho/researcher/report-view";
import { useReports } from "@/components/basho/reports-query";
import { RequirePersona, Shell } from "@/components/basho/shell";
import { ErrorBox, Loading } from "@/components/basho/ui";
import type { DemoContext } from "@/lib/types";

function ResearcherWork({ ctx, userId }: { ctx: DemoContext; userId: string }) {
  const reports = useReports(ctx);
  const mine = reports.data?.find((r) => r.status.researcher_id === userId);
  return (
    <div className="space-y-6">
      <EvidencePanel ctx={ctx} userId={userId} />
      {reports.isPending && <Loading />}
      {reports.isError && <ErrorBox error={reports.error} onRetry={() => void reports.refetch()} />}
      {reports.data && (mine ? <ReportView key={mine.status.researcher_id} ctx={ctx} current={mine} canAct /> : <ReportBuilder ctx={ctx} researcherId={userId} />)}
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
