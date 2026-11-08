"use client";

import Link from "next/link";
import { useDemoUser } from "@/components/auth/session-provider";
import { PageHeader, Section } from "@/components/layout/page-header";
import { PendingInbox } from "@/components/pending/pending-inbox";
import { ReviewStateBadge } from "@/components/status/badges";
import { EmptyState, ErrorState, LoadingState } from "@/components/status/states";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useProjectContext, useReports } from "@/lib/queries";

export function ResearcherHome() {
  const user = useDemoUser();
  const context = useProjectContext();
  const reports = useReports(context.data?.period.id);
  if (context.isPending) return <LoadingState />;
  if (context.isError) return <ErrorState error={context.error} onRetry={() => context.refetch()} />;
  const mine = reports.data?.filter(report => report.author_id === user.personId) ?? [];
  return (
    <div className="space-y-8">
      <PageHeader title="Meus relatórios" subtitle={context.data.project.name + " · " + context.data.period.label} />
      <Section title="Relatórios do período">
        {reports.isPending && <LoadingState />}
        {reports.isError && <ErrorState error={reports.error} onRetry={() => reports.refetch()} />}
        {reports.isSuccess && mine.length === 0 && <EmptyState title="Nenhum relatório neste período." />}
        <div className="grid gap-3 sm:grid-cols-2">
          {mine.map(report => <Card key={report.report_id}>
            <CardHeader><CardTitle className="flex flex-wrap items-center gap-2 text-base">
              Relatório mensal · v{report.latest_version} <ReviewStateBadge state={report.review_state} />
            </CardTitle></CardHeader>
            <CardContent><Link href={"/pesquisador/relatorios/" + report.report_id} className="font-medium text-primary underline underline-offset-4">Ler e revisar relatório</Link></CardContent>
          </Card>)}
        </div>
      </Section>
      <Section title="Minhas pendências"><PendingInbox role="researcher" personId={user.personId} /></Section>
    </div>
  );
}
