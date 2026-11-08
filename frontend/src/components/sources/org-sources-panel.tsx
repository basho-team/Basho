"use client";

import { CheckCircle2, CircleDashed, GitPullRequest, HardDrive, NotebookPen, ShieldCheck } from "lucide-react";
import { PageHeader } from "@/components/layout/page-header";
import { ErrorState, LoadingState } from "@/components/status/states";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { SourceSummary } from "@/lib/bff/integrations-contract";
import { publicEnv } from "@/lib/env";
import { useOrgSources } from "@/lib/integrations/hooks";

/**
 * Fontes da organização: GitHub, Notion e Google Drive conectados uma vez para a empresa
 * (ADR-0012). O pesquisador não cola links; a tela mostra o que o Basho já leu para o projeto.
 */

const META: Record<SourceSummary["source"], { label: string; icon: typeof GitPullRequest; unit: string }> = {
  github: { label: "GitHub", icon: GitPullRequest, unit: "commits e PRs" },
  notion: { label: "Notion", icon: NotebookPen, unit: "páginas" },
  google_drive: { label: "Google Drive", icon: HardDrive, unit: "documentos" },
};

const dateFormat = new Intl.DateTimeFormat("pt-BR", { dateStyle: "short", timeStyle: "short" });

function SourceCard({ item }: { item: SourceSummary }) {
  const { label, icon: Icon, unit } = META[item.source];
  const connected = item.events > 0;
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          <Icon className="size-4 text-primary" aria-hidden />
          {label}
          {connected ? (
            <Badge variant="secondary" className="gap-1"><CheckCircle2 className="size-3" aria-hidden /> Lendo</Badge>
          ) : (
            <Badge variant="outline" className="gap-1"><CircleDashed className="size-3" aria-hidden /> Sem leituras</Badge>
          )}
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-1.5 text-sm">
        <p>
          <span className="text-2xl font-semibold tabular-nums">{item.documents}</span>{" "}
          <span className="text-muted-foreground">{unit}</span>
        </p>
        <p className="text-muted-foreground">
          {item.last_seen_at
            ? `Última leitura: ${dateFormat.format(new Date(item.last_seen_at))}`
            : "Ainda não lido neste projeto. A leitura acontece quando um relatório é preparado."}
        </p>
        {item.scopes.length > 0 && (
          <p className="font-mono text-xs break-all text-muted-foreground">{item.scopes.join(", ")}</p>
        )}
      </CardContent>
    </Card>
  );
}

export function OrgSourcesPanel() {
  const projectId = publicEnv.NEXT_PUBLIC_BASHO_PROJECT_ID;
  const sources = useOrgSources(projectId);
  return (
    <div className="space-y-6">
      <PageHeader
        title="Integrações"
        subtitle="GitHub, Notion e Google Drive já conectados pela organização. Ninguém precisa colar links: o Basho lê as fontes e registra cada evidência com origem e versão."
      />
      <Alert>
        <ShieldCheck aria-hidden />
        <AlertTitle>Somente leitura</AlertTitle>
        <AlertDescription>
          O Basho só lê. O conteúdo das fontes é tratado como evidência, nunca como instrução. Para mudar quais
          repositórios, pastas ou páginas são lidos, fale com o gerente do projeto.
        </AlertDescription>
      </Alert>
      {!projectId && <ErrorState error={new Error("Projeto da demonstração não configurado (NEXT_PUBLIC_BASHO_PROJECT_ID).")} />}
      {sources.isPending && projectId && <LoadingState />}
      {sources.isError && <ErrorState error={sources.error} onRetry={() => sources.refetch()} />}
      {sources.isSuccess && (
        <div className="grid gap-4 md:grid-cols-3">
          {sources.data.sources.map(item => <SourceCard key={item.source} item={item} />)}
        </div>
      )}
    </div>
  );
}
