"use client";

import Link from "next/link";
import { useState } from "react";
import { PageHeader, Section } from "@/components/layout/page-header";
import { PendingInbox } from "@/components/pending/pending-inbox";
import { ReviewStateBadge } from "@/components/status/badges";
import { EmptyState, ErrorState, LoadingState } from "@/components/status/states";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useProjectContext, useReports } from "@/lib/queries";

export function ResearcherHome() {
  const context = useProjectContext();
  const reports = useReports(context.data?.period.id);
  const researchers = context.data?.people.filter((p) => p.role === "researcher") ?? [];
  const [personId, setPersonId] = useState("p-ana");

  if (context.isPending) return <LoadingState />;
  if (context.isError) return <ErrorState error={context.error} onRetry={() => context.refetch()} />;

  const mine = reports.data?.filter((r) => r.author_id === personId) ?? [];

  return (
    <div className="space-y-8">
      <PageHeader
        title="Meus relatórios"
        subtitle={`${context.data.project.name} · ${context.data.period.label}`}
        actions={
          <div className="flex items-center gap-1" role="group" aria-label="Atuar como (demonstração)">
            <span className="mr-1 text-xs text-muted-foreground">Atuar como (demo):</span>
            {researchers.map((p) => (
              <Button
                key={p.id}
                size="sm"
                variant={p.id === personId ? "default" : "outline"}
                aria-pressed={p.id === personId}
                onClick={() => setPersonId(p.id)}
              >
                {p.name}
              </Button>
            ))}
          </div>
        }
      />

      <Section title="Relatórios do período">
        {reports.isPending && <LoadingState />}
        {reports.isError && <ErrorState error={reports.error} onRetry={() => reports.refetch()} />}
        {reports.isSuccess && mine.length === 0 && <EmptyState title="Nenhum relatório neste período." />}
        <div className="grid gap-3 sm:grid-cols-2">
          {mine.map((report) => (
            <Card key={report.report_id}>
              <CardHeader>
                <CardTitle className="flex flex-wrap items-center gap-2 text-base">
                  Relatório mensal · v{report.latest_version}
                  <ReviewStateBadge state={report.review_state} />
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-3 text-sm">
                <p className="text-muted-foreground">
                  {report.pending_claims} afirmação(ões) pendente(s) · {report.open_gaps} lacuna(s) ·{" "}
                  {report.approved_by_researcher ? "você aprovou esta versão" : "aguardando sua revisão"}
                </p>
                <Button render={<Link href={`/pesquisador/relatorios/${report.report_id}`} />} nativeButton={false}>
                  Revisar relatório
                </Button>
              </CardContent>
            </Card>
          ))}
        </div>
      </Section>

      <Section title="Pendências para você">
        <PendingInbox role="researcher" personId={personId} />
      </Section>
    </div>
  );
}
