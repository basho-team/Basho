"use client";

import { useEffect, useState } from "react";
import { CheckCircle2, GitPullRequest, HardDrive, NotebookPen, RefreshCw } from "lucide-react";
import { useDemoUser } from "@/components/auth/session-provider";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { PageHeader } from "@/components/layout/page-header";
import { IntegrationOverviewSchema, type IntegrationOverview, type IntegrationProvider } from "@/lib/integrations/shared";

const ICON = { github: GitPullRequest, notion: NotebookPen, drive: HardDrive };

function useIntegrations() {
  const [overview, setOverview] = useState<IntegrationOverview | null>(null);
  const [message, setMessage] = useState("");
  const [pending, setPending] = useState<IntegrationProvider | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    const controller = new AbortController();
    fetch("/api/integrations", { cache: "no-store", signal: controller.signal })
      .then(async response => {
        if (!response.ok) throw new Error("Não foi possível carregar as integrações.");
        setOverview(IntegrationOverviewSchema.parse(await response.json()));
      }).catch(reason => {
        if (!controller.signal.aborted) setError(reason instanceof Error ? reason.message : "Falha na leitura.");
      });
    return () => controller.abort();
  }, []);

  async function act(provider: IntegrationProvider, action: "verify" | "sync" | "enable" | "disable") {
    setPending(provider); setMessage(""); setError("");
    try {
      const response = await fetch("/api/integrations", {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ provider, action }),
      });
      const body = await response.json();
      if (!response.ok) { setError(body.message ?? "Não foi possível concluir."); return; }
      setOverview(IntegrationOverviewSchema.parse(body));
      setMessage(action === "verify" ? "Leitura das fontes disponíveis verificada." : "Fontes atualizadas.");
    } catch { setError("Não foi possível conectar ao servidor."); } finally { setPending(null); }
  }

  return { overview, message, pending, error, act };
}

type Integration = IntegrationOverview["integrations"][number];
type IntegrationState = ReturnType<typeof useIntegrations>;

function IntegrationCard({ integration, state, role }: {
  integration: Integration; state: IntegrationState; role: ReturnType<typeof useDemoUser>["role"];
}) {
  const { pending, act } = state;
        const Icon = ICON[integration.provider];
        return <Card data-provider={integration.provider}>
          <CardHeader><CardTitle className="flex items-center gap-2"><Icon className="size-5" aria-hidden />{integration.name}</CardTitle>
            <span className="w-fit rounded-full bg-muted px-2 py-1 text-xs">{integration.enabled ? "Fontes disponíveis" : "Fontes desativadas"}</span>
          </CardHeader>
          <CardContent className="space-y-4">
            <p className="text-sm leading-relaxed text-muted-foreground">{integration.implementation}</p>
            <p className="text-xs text-muted-foreground">{role === "researcher" ? "Somente fontes vinculadas ao seu trabalho." : role === "fiscal" ? "Leitura de fontes e documentos. Configuração reservada ao gerente." : "Você pode configurar e atualizar as fontes da organização."}</p>
            <ul className="space-y-3">
              {integration.sources.map(source => <li key={source.id} className="rounded-lg border p-3 text-sm">
                <p className="font-medium">{source.title}</p><p className="mt-1 text-muted-foreground">{source.excerpt}</p>
                <p className="mt-2 break-all font-mono text-xs text-muted-foreground">{source.locator} · {source.revision}</p>
              </li>)}
            </ul>
            {integration.sources.length === 0 && <p className="text-sm text-muted-foreground">Nenhuma fonte disponível.</p>}
            <div className="flex flex-wrap gap-2">
              <Button size="sm" variant="outline" disabled={!integration.enabled || pending !== null}
                onClick={() => act(integration.provider, "verify")}><RefreshCw className="size-3.5" aria-hidden />Verificar leitura</Button>
              {integration.canConfigure && <>
                <Button size="sm" variant="outline" disabled={!integration.enabled || pending !== null}
                  onClick={() => act(integration.provider, "sync")}>Atualizar fontes</Button>
                <Button size="sm" variant="ghost" disabled={pending !== null}
                  onClick={() => act(integration.provider, integration.enabled ? "disable" : "enable")}>{integration.enabled ? "Desativar fontes" : "Ativar fontes"}</Button>
              </>}
            </div>
            {integration.checkedAt && <p className="text-xs text-muted-foreground">Última verificação: {new Date(integration.checkedAt).toLocaleString("pt-BR")}</p>}
          </CardContent>
        </Card>;
}

export function IntegrationsView() {
  const user = useDemoUser();
  const state = useIntegrations();
  const { overview, message, error } = state;
  return <div className="space-y-6">
    <PageHeader title="Fontes e integrações" subtitle="Acompanhe o que está disponível para sua função na organização." />
    {message && <p role="status" className="flex items-start gap-2 rounded-lg bg-primary/10 p-3 text-sm text-primary"><CheckCircle2 className="size-4 shrink-0" aria-hidden />{message}</p>}
    {error && <p role="alert" className="rounded-lg border border-destructive/30 p-3 text-sm text-destructive">{error}</p>}
    {!overview && !error && <p className="text-muted-foreground">Carregando fontes…</p>}
    <div className="grid gap-4 xl:grid-cols-3">
      {overview?.integrations.map(integration =>
        <IntegrationCard key={integration.provider} integration={integration} state={state} role={user.role} />)}
    </div>
  </div>;
}
