"use client";

import { ExternalLink, FolderSync, Sparkles } from "lucide-react";
import { useState } from "react";
import { TextField } from "@/components/forms/text-field";
import { EmptyState, ErrorState, LoadingState } from "@/components/status/states";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import {
  isSafeExternalUrl,
  LINK_KIND_LABEL,
  type IntegrationsConfig,
  type ProjectLink,
  type Publication,
  type PublicationStatus,
  type RunStatus,
} from "@/lib/bff/integrations-contract";
import {
  useAddLink,
  useGenerate,
  useIntegrationsConfig,
  useLinks,
  usePublications,
  usePublishNow,
  useRevokeLink,
  useRun,
} from "@/lib/integrations/hooks";

const STATUS_LABEL: Record<PublicationStatus, string> = {
  queued: "Na fila",
  running: "Publicando…",
  published: "Publicado",
  failed: "Falhou",
};

const RUN_LABEL: Record<RunStatus, string> = {
  queued: "Na fila do agente",
  running: "O agente está lendo as evidências e escrevendo…",
  awaiting_input: "Aguardando uma resposta humana",
  completed: "Relatório gerado",
  failed: "O agente não conseguiu gerar o relatório",
};

/** Explica por que uma publicação falhou, sem expor detalhe do provedor. */
const FAILURE_HINT: Record<string, string> = {
  access_denied: "O Basho perdeu a permissão de edição. Compartilhe a pasta/página de novo.",
  not_found: "Pasta ou página não encontrada. Confira se ainda existe e está compartilhada.",
  unauthorized: "Credencial do Basho recusada pelo serviço.",
  not_configured: "Integração não configurada no servidor.",
  link_unavailable: "O link foi revogado.",
  artifact_not_publishable: "O registro foi rejeitado ou corrigido depois de enfileirado.",
  unavailable: "Serviço externo indisponível.",
  rate_limited: "Limite do serviço externo atingido.",
};

function ShareHint({ config }: { config: IntegrationsConfig | undefined }) {
  if (!config) return null;
  return (
    <ul className="list-disc space-y-1 pl-5 text-sm text-muted-foreground">
      <li>
        <strong>Google Drive:</strong>{" "}
        {config.drive && config.google_service_account_email ? (
          <>
            compartilhe a pasta como <em>Editor</em> com{" "}
            <code className="font-mono">{config.google_service_account_email}</code> e cole o link dela.
          </>
        ) : (
          "não configurado neste servidor."
        )}
      </li>
      <li>
        <strong>Notion:</strong>{" "}
        {config.notion
          ? "na página, abra ••• → Conexões e adicione a integração do Basho; depois cole o link da página."
          : "não configurado neste servidor."}
      </li>
      <li>
        <strong>GitHub:</strong> cole o link do repositório (<code className="font-mono">github.com/dono/nome</code>); é de onde o
        Basho lê commits e PRs.
      </li>
    </ul>
  );
}

function ConnectCard({ projectId, config }: { projectId: string; config: IntegrationsConfig | undefined }) {
  const [url, setUrl] = useState("");
  const add = useAddLink(projectId);
  const submit = () => add.mutate(url.trim(), { onSuccess: () => setUrl("") });
  return (
    <Card>
      <CardHeader>
        <CardTitle>Conectar um link</CardTitle>
        <CardDescription>
          Cole o link de uma pasta do Drive, de uma página do Notion ou de um repositório do GitHub. O Basho confere o acesso antes de
          conectar.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        <TextField label="Link" value={url} onChange={setUrl} rows={1} placeholder="https://drive.google.com/drive/folders/…" />
        {add.isError && <ErrorState error={add.error} onRetry={() => add.reset()} />}
        {add.isSuccess && (
          <Alert>
            <AlertTitle>Conectado</AlertTitle>
            <AlertDescription>{add.data.display_name} está autorizado.</AlertDescription>
          </Alert>
        )}
        <Button disabled={add.isPending || url.trim().length < 8} onClick={submit}>
          {add.isPending ? "Conferindo acesso…" : "Conectar"}
        </Button>
        <ShareHint config={config} />
      </CardContent>
    </Card>
  );
}

function LinksCard({ projectId }: { projectId: string }) {
  const links = useLinks(projectId);
  const revoke = useRevokeLink(projectId);
  return (
    <Card>
      <CardHeader>
        <CardTitle>Links autorizados</CardTitle>
        <CardDescription>O Basho só lê e escreve nos links desta lista. Revogar interrompe novas publicações.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-2">
        {links.isPending && <LoadingState />}
        {links.isError && <ErrorState error={links.error} onRetry={() => links.refetch()} />}
        {links.data?.length === 0 && <EmptyState title="Nenhum link conectado ainda." />}
        {revoke.isError && <ErrorState error={revoke.error} onRetry={() => revoke.reset()} />}
        {links.data?.map((link: ProjectLink) => (
          <div key={link.id} className="flex flex-wrap items-center justify-between gap-2 rounded-lg border p-3 text-sm">
            <div className="min-w-0">
              <p className="font-medium">{link.display_name}</p>
              <p className="text-muted-foreground">{LINK_KIND_LABEL[link.kind]}</p>
            </div>
            <div className="flex items-center gap-2">
              <Badge variant={link.status === "active" ? "secondary" : "outline"}>
                {link.status === "active" ? "Ativo" : "Revogado"}
              </Badge>
              {link.status === "active" && (
                <Button size="sm" variant="outline" disabled={revoke.isPending} onClick={() => revoke.mutate(link.id)}>
                  Revogar
                </Button>
              )}
            </div>
          </div>
        ))}
      </CardContent>
    </Card>
  );
}

function GenerateCard({ projectId }: { projectId: string }) {
  const generate = useGenerate(projectId);
  const run = useRun(generate.data?.id, projectId);
  const current = run.data ?? generate.data;
  const needsPerson = current?.status === "completed" && current.artifact_status === "needs_human";
  return (
    <Card>
      <CardHeader>
        <CardTitle>Gerar relatório a partir do GitHub</CardTitle>
        <CardDescription>
          O agente lê os commits e PRs do repositório conectado, escreve o relatório citando cada fonte e o Checker confere. Se estiver
          tudo sustentado, ele é publicado sozinho na pasta BASHO.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        <Button disabled={generate.isPending || current?.status === "queued" || current?.status === "running"} onClick={() => generate.mutate()}>
          <Sparkles aria-hidden /> {generate.isPending ? "Pedindo…" : "Gerar relatório dos últimos 30 dias"}
        </Button>
        {generate.isError && <ErrorState error={generate.error} onRetry={() => generate.reset()} />}
        {current && (
          <div className="space-y-1 text-sm">
            <p>
              <Badge variant={current.status === "failed" ? "destructive" : current.status === "completed" ? "default" : "secondary"}>
                {RUN_LABEL[current.status]}
              </Badge>{" "}
              {current.attempts > 0 && current.status !== "completed" && (
                <span className="text-muted-foreground">
                  tentativa {current.attempts} de {current.max_attempts}
                </span>
              )}
            </p>
            {current.error && <p className="text-muted-foreground">{current.error.message}</p>}
            {current.status === "completed" && current.artifact_status === "verified" && (
              <p className="text-muted-foreground">Verificado pelo Checker: a publicação entra na fila sozinha.</p>
            )}
            {needsPerson && (
              <p className="text-muted-foreground">
                O Checker apontou divergência. Nada foi publicado; veja as pendências para o responsável.
              </p>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function PublicationRow({ item }: { item: Publication }) {
  const hint = item.error_code ? (FAILURE_HINT[item.error_code] ?? item.error_code) : null;
  const badgeVariant = item.status === "failed" ? "destructive" : item.status === "published" ? "default" : "secondary";
  return (
    <div className="flex flex-wrap items-center justify-between gap-2 rounded-lg border p-3 text-sm">
      <div className="min-w-0">
        <p className="font-medium">{item.title}</p>
        <p className="text-muted-foreground">
          {item.link_kind ? LINK_KIND_LABEL[item.link_kind] : "Destino removido"}
          {item.status === "failed" && hint ? ` · ${hint}` : ""}
          {item.status === "queued" && item.attempts > 0 && hint ? ` · tentando de novo (${hint})` : ""}
        </p>
      </div>
      <div className="flex items-center gap-2">
        <Badge variant={badgeVariant}>{STATUS_LABEL[item.status]}</Badge>
        {item.status === "published" && isSafeExternalUrl(item.external_url) && (
          <a
            className="inline-flex items-center gap-1 text-primary underline-offset-4 hover:underline"
            href={item.external_url}
            target="_blank"
            rel="noopener noreferrer"
          >
            Abrir <ExternalLink className="size-3" aria-hidden />
          </a>
        )}
      </div>
    </div>
  );
}

function PublicationsCard({ projectId, canPublish }: { projectId: string; canPublish: boolean }) {
  const publications = usePublications(projectId);
  const publish = usePublishNow(projectId);
  return (
    <Card>
      <CardHeader>
        <CardTitle>Relatórios publicados na pasta BASHO</CardTitle>
        <CardDescription>
          Relatórios verificados pelo Checker são publicados sozinhos, sem aprovação de rotina. O que falta ou diverge vira pendência
          para o responsável, e o texto diz “potencialmente qualificável, sujeito a análise”.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="flex flex-wrap items-center gap-3">
          <Button disabled={!canPublish || publish.isPending} onClick={() => publish.mutate()}>
            <FolderSync aria-hidden /> {publish.isPending ? "Enfileirando…" : "Publicar agora"}
          </Button>
          {!canPublish && <span className="text-sm text-muted-foreground">Conecte uma pasta do Drive ou uma página do Notion.</span>}
          {publish.isSuccess && (
            <span className="text-sm text-muted-foreground">
              {publish.data.queued === 0 ? "Nada novo para publicar." : `${publish.data.queued} documento(s) enfileirado(s).`}
            </span>
          )}
        </div>
        {publish.isError && <ErrorState error={publish.error} onRetry={() => publish.reset()} />}
        {publications.isPending && <LoadingState />}
        {publications.isError && <ErrorState error={publications.error} onRetry={() => publications.refetch()} />}
        {publications.data?.items.length === 0 && <EmptyState title="Nenhum relatório publicado ainda." />}
        {publications.data?.items.map((item) => <PublicationRow key={item.id} item={item} />)}
      </CardContent>
    </Card>
  );
}

export function IntegrationsPanel({ projectId }: { projectId: string }) {
  const config = useIntegrationsConfig();
  const links = useLinks(projectId);
  const canPublish = (links.data ?? []).some(
    (link) => link.status === "active" && (link.kind === "drive_folder" || link.kind === "notion_page"),
  );
  return (
    <div className="space-y-6">
      <ConnectCard projectId={projectId} config={config.data} />
      <LinksCard projectId={projectId} />
      <GenerateCard projectId={projectId} />
      <PublicationsCard projectId={projectId} canPublish={canPublish} />
    </div>
  );
}
