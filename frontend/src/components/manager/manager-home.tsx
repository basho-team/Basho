"use client";

import { PageHeader, Section } from "@/components/layout/page-header";
import { ClarificationForm } from "@/components/manager/clarification-form";
import { ForwardPanel } from "@/components/manager/forward-panel";
import { PendingInbox } from "@/components/pending/pending-inbox";
import { ReviewStateBadge } from "@/components/status/badges";
import { RunStatus } from "@/components/status/run-status";
import { EmptyState, ErrorState, LoadingState } from "@/components/status/states";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import type { Consolidation } from "@/lib/contracts/provisional";
import { isRunActive, useConsolidation, useProjectContext, useTriggerClosing } from "@/lib/queries";

function ReportsTable({ consolidation }: { consolidation: Consolidation }) {
  return (
    <div className="overflow-x-auto rounded-lg border">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Pesquisador</TableHead>
            <TableHead>Versão</TableHead>
            <TableHead>Revisão</TableHead>
            <TableHead>Pendências</TableHead>
            <TableHead className="text-right">Ação</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {consolidation.reports.map((r) => (
            <TableRow key={r.report_id}>
              <TableCell className="font-medium">{r.author_name}</TableCell>
              <TableCell>v{r.latest_version}</TableCell>
              <TableCell className="space-x-1">
                <Badge variant={r.approved_by_researcher ? "secondary" : "outline"}>
                  {r.approved_by_researcher ? "Revisado" : "Rascunho pendente"}
                </Badge>
                <ReviewStateBadge state={r.review_state} />
              </TableCell>
              <TableCell className="text-muted-foreground">
                {r.pending_claims} afirmação(ões) · {r.open_gaps} lacuna(s)
              </TableCell>
              <TableCell className="text-right">
                <ClarificationForm reportId={r.report_id} authorName={r.author_name} />
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}

function BulletList({ items, empty }: { items: string[]; empty: string }) {
  if (items.length === 0) return <p className="text-sm text-muted-foreground">{empty}</p>;
  return (
    <ul className="list-disc space-y-1 pl-5 text-sm">
      {items.map((item) => (
        <li key={item}>{item}</li>
      ))}
    </ul>
  );
}

export function ManagerHome() {
  const context = useProjectContext();
  const consolidation = useConsolidation(context.data?.period.id);
  const closing = useTriggerClosing();

  if (context.isError) return <ErrorState error={context.error} onRetry={() => context.refetch()} />;
  if (consolidation.isError) return <ErrorState error={consolidation.error} onRetry={() => consolidation.refetch()} />;
  if (context.isPending || consolidation.isPending) return <LoadingState label="Carregando consolidação…" />;

  const data = consolidation.data;
  const running = isRunActive(data.last_run);

  return (
    <div className="space-y-8">
      <PageHeader
        title="Consolidação do período"
        subtitle={`${context.data.project.name} · ${context.data.period.label}`}
        actions={
          <Button
            variant="outline"
            disabled={running || closing.isPending}
            onClick={() => closing.mutate(data.period_id)}
          >
            Disparar fechamento do período
          </Button>
        }
      />
      {data.last_run && <RunStatus run={data.last_run} />}
      {closing.isError && <ErrorState error={closing.error} onRetry={() => closing.mutate(data.period_id)} />}

      <Section title="Relatórios individuais">
        {data.reports.length === 0 ? <EmptyState title="Nenhum relatório no período." /> : <ReportsTable consolidation={data} />}
      </Section>

      <div className="grid gap-6 md:grid-cols-2">
        <Section title="Avanços e entregas">
          <BulletList items={data.highlights} empty="Nenhum avanço registrado." />
        </Section>
        <Section title="Problemas">
          <BulletList items={data.problems} empty="Nenhum problema registrado." />
        </Section>
      </div>

      <Section title="Pendências em aberto no projeto">
        <BulletList
          items={data.open_requests.map((r) => `${r.target.label}: ${r.reason} (${r.status === "open" ? "aberta" : "respondida, em reanálise"})`)}
          empty="Nenhuma pendência em aberto."
        />
      </Section>

      <ForwardPanel consolidation={data} />

      <Section title="Pendências para você">
        <PendingInbox role="manager" personId="p-marina" />
      </Section>
    </div>
  );
}
