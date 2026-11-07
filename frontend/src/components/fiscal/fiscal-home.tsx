"use client";

import { ExpensesTable } from "@/components/fiscal/expenses-table";
import { FindingCard } from "@/components/fiscal/finding-card";
import { PageHeader } from "@/components/layout/page-header";
import { RunStatus } from "@/components/status/run-status";
import { AwaitingState, ErrorState, LoadingState, StaleBanner } from "@/components/status/states";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import type { FiscalPackage } from "@/lib/contracts/provisional";
import { useFiscalPackage, useProjectContext } from "@/lib/queries";

const dateFormat = new Intl.DateTimeFormat("pt-BR", { dateStyle: "short", timeStyle: "short" });

function PackageSummary({ pkg }: { pkg: FiscalPackage }) {
  return (
    <div className="space-y-3 text-sm">
      {pkg.forwarded_at && <p>Encaminhado pelo gerente em {dateFormat.format(new Date(pkg.forwarded_at))}.</p>}
      <ul className="list-disc space-y-1 pl-5">
        {pkg.report_versions.map((v) => (
          <li key={v.id}>
            Relatório de {v.author_name}, versão v{v.version}
          </li>
        ))}
      </ul>
      <p className="text-muted-foreground">
        Pendências em aberto: {pkg.open_requests.length}. Despesas excluídas continuam listadas com o motivo. Nenhum
        envio ao MCTI é feito pelo sistema: a submissão do FORMP&amp;D é humana.
      </p>
    </div>
  );
}

export function FiscalHome() {
  const context = useProjectContext();
  const pkg = useFiscalPackage(context.data?.period.id);

  if (context.isError) return <ErrorState error={context.error} onRetry={() => context.refetch()} />;
  if (pkg.isError) return <ErrorState error={pkg.error} onRetry={() => pkg.refetch()} />;
  if (context.isPending || pkg.isPending) return <LoadingState label="Carregando pacote…" />;

  const data = pkg.data;

  return (
    <div className="space-y-6">
      <PageHeader
        title="Análise fiscal"
        subtitle={`${context.data.project.name} · ${context.data.period.label} · sinalizações não são garantia de benefício`}
      />
      {!data.available && (
        <AwaitingState title="Aguardando encaminhamento do gerente">
          O que aparece abaixo é análise preliminar. O pacote revisado chega quando o gerente encaminhar.
        </AwaitingState>
      )}
      {data.stale && data.stale_reason && <StaleBanner reason={data.stale_reason} />}
      {data.last_run && <RunStatus run={data.last_run} />}

      <Tabs defaultValue="findings">
        <TabsList>
          <TabsTrigger value="findings">Sinalizações ({data.findings.length})</TabsTrigger>
          <TabsTrigger value="expenses">Despesas ({data.expenses.length})</TabsTrigger>
          <TabsTrigger value="package">Pacote</TabsTrigger>
        </TabsList>
        <TabsContent value="findings" className="space-y-4">
          {data.findings.map((f) => (
            <FindingCard
              key={f.id}
              finding={f}
              evidence={data.evidence}
              decisions={data.decisions.filter((d) => d.finding_id === f.id)}
            />
          ))}
        </TabsContent>
        <TabsContent value="expenses">
          <ExpensesTable expenses={data.expenses} />
        </TabsContent>
        <TabsContent value="package">
          <PackageSummary pkg={data} />
        </TabsContent>
      </Tabs>
    </div>
  );
}
