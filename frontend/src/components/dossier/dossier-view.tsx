"use client";

import { useState } from "react";
import { PageHeader, Section } from "@/components/layout/page-header";
import { ArtifactStatusBadge, SyntheticBadge } from "@/components/status/badges";
import { ErrorState, LoadingState, EmptyState } from "@/components/status/states";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { ArtifactStatus, DossierEntry, EvidenceEvent } from "@/lib/api/projects";
import { useDossier } from "@/lib/queries";

const dateFormat = new Intl.DateTimeFormat("pt-BR", { dateStyle: "short", timeStyle: "short" });
const money = new Intl.NumberFormat("pt-BR", { style: "currency", currency: "USD", maximumFractionDigits: 4 });

const KIND_LABEL: Record<string, string> = {
  commit_observed: "Commit",
  pull_request_observed: "Pull request",
  issue_observed: "Issue",
  document_observed: "Documento",
  technical_justification: "Justificativa técnica",
  activity_record: "Registro do Maker",
  formal_hours_declared: "Horas formais declaradas",
  expense_declared: "Despesa declarada",
  user_confirmation: "Confirmação humana",
  user_correction: "Correção humana",
  verification_result: "Verificação",
  status_changed: "Mudança de estado",
};

/** `owner/repo#42` → link do GitHub. Qualquer outro formato fica como texto (dado externo). */
const GITHUB_REF = /^([\w.-]+\/[\w.-]+)#(\d+)$/;

const SOURCE_LABEL: Record<string, string> = {
  github: "GitHub",
  google_drive: "Google Drive",
  notion: "Notion",
};

/** Link do documento (Drive/Notion) só se for https em host conhecido: o payload é dado externo. */
const DOCUMENT_HOSTS = new Set(["docs.google.com", "drive.google.com", "www.notion.so", "notion.so"]);

function documentLink(event: EvidenceEvent): { href: string; title: string } | null {
  if (event.kind !== "document_observed") return null;
  const { url, title } = event.payload as { url?: unknown; title?: unknown };
  if (typeof url !== "string") return null;
  try {
    const parsed = new URL(url);
    if (parsed.protocol !== "https:" || !DOCUMENT_HOSTS.has(parsed.hostname)) return null;
  } catch {
    return null;
  }
  return { href: url, title: typeof title === "string" && title ? title : url };
}

function SourceRef({ event }: { event: EvidenceEvent }) {
  const ref = event.source_ref;
  if (!ref) return null;
  const doc = documentLink(event);
  if (doc) {
    return (
      <a className="break-all underline" href={doc.href} target="_blank" rel="noopener noreferrer">
        {doc.title} <span className="font-mono text-muted-foreground">({ref})</span>
      </a>
    );
  }
  const match = event.source === "github" ? GITHUB_REF.exec(ref) : null;
  if (!match) return <span className="font-mono break-all">{ref}</span>;
  return (
    <a
      className="font-mono break-all underline"
      href={`https://github.com/${match[1]}/issues/${match[2]}`}
      target="_blank"
      rel="noopener noreferrer"
    >
      {ref}
    </a>
  );
}

function EventLine({ event, artifactId }: { event: EvidenceEvent; artifactId: string }) {
  return (
    <li className="space-y-0.5 rounded-md border p-2 text-xs">
      <div className="flex flex-wrap items-center gap-2">
        <span className="font-medium">{KIND_LABEL[event.kind] ?? event.kind}</span>
        <span className="text-muted-foreground">
          {SOURCE_LABEL[event.source] ?? event.source} · {event.actor.type}
          {event.actor.model ? ` (${event.actor.model})` : ""} · {dateFormat.format(new Date(event.created_at))}
        </span>
        {event.is_synthetic && <SyntheticBadge />}
        {event.supersedes && (
          <Badge variant="outline">substitui {event.supersedes === artifactId ? "o registro original" : event.supersedes.slice(0, 8)}</Badge>
        )}
      </div>
      <SourceRef event={event} />
    </li>
  );
}

function EntryCard({ entry }: { entry: DossierEntry }) {
  return (
    <Card className={entry.status === "needs_review" ? "border-amber-400 dark:border-amber-700" : undefined}>
      <CardHeader>
        <CardTitle className="flex flex-wrap items-center gap-2 text-base">
          {entry.title}
          <ArtifactStatusBadge status={entry.status} />
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4 text-sm">
        {entry.status === "needs_review" && (
          <p className="text-amber-900 dark:text-amber-200">
            Uma evidência deste item foi corrigida ou substituída: ele precisa de nova revisão humana.
          </p>
        )}
        {entry.approval && (
          <p>
            Decisão formal: <strong>{entry.approval.decision === "approve" ? "aprovado" : "rejeitado"}</strong> em{" "}
            {dateFormat.format(new Date(entry.approval.created_at))}
            {entry.approval.comment && <> · “{entry.approval.comment}”</>}
          </p>
        )}

        <div className="space-y-1">
          <h3 className="font-medium">Evidências citadas ({entry.evidence.length})</h3>
          {entry.evidence.length === 0 ? (
            <p className="text-muted-foreground">Sem evidência vinculada.</p>
          ) : (
            <ul className="space-y-1">
              {entry.evidence.map((e) => (
                <EventLine key={e.id} event={e} artifactId={entry.artifact_id} />
              ))}
            </ul>
          )}
        </div>

        {entry.verifications.length > 0 && (
          <div className="space-y-1">
            <h3 className="font-medium">Verificações</h3>
            <ul className="space-y-1">
              {entry.verifications.map((v, index) => (
                <li key={`${v.checker}-${index}`} className="rounded-md border p-2 text-xs">
                  <span className="font-medium">{v.verdict === "pass" ? "Passou" : "Não passou"}</span> · {v.checker}
                  {v.issues.map((issue) => (
                    <p key={`${issue.code}-${issue.message}`} className="text-muted-foreground">
                      {issue.code}: {issue.message}
                    </p>
                  ))}
                </li>
              ))}
            </ul>
          </div>
        )}

        <div className="space-y-1">
          <h3 className="font-medium">Histórico (o que foi substituído continua aqui)</h3>
          <ol className="space-y-1">
            {entry.history.map((e) => (
              <EventLine key={e.id} event={e} artifactId={entry.artifact_id} />
            ))}
          </ol>
        </div>

        {entry.runs.length > 0 && (
          <div className="space-y-1">
            <h3 className="font-medium">Execuções do agente</h3>
            <ul className="text-xs text-muted-foreground">
              {entry.runs.map((run) => (
                <li key={run.run_id}>
                  {run.model} · {run.input_tokens} → {run.output_tokens} tokens · {(run.latency_ms / 1000).toFixed(1)} s ·{" "}
                  {money.format(run.cost_usd)}
                </li>
              ))}
            </ul>
          </div>
        )}

        <details className="text-xs">
          <summary className="cursor-pointer text-muted-foreground">Conteúdo do registro</summary>
          <pre className="mt-1 overflow-x-auto rounded-md bg-muted p-2 whitespace-pre-wrap">
            {JSON.stringify(entry.content, null, 2)}
          </pre>
        </details>
      </CardContent>
    </Card>
  );
}

/** Dossiê do projeto (#13): só leitura. Estados vêm do backend; a UI filtra para exibir. */
export function DossierView() {
  const dossier = useDossier();
  const [filter, setFilter] = useState<ArtifactStatus | "all">("all");

  if (dossier.isPending) return <LoadingState label="Carregando dossiê…" />;
  if (dossier.isError) return <ErrorState error={dossier.error} onRetry={() => dossier.refetch()} />;

  const { project, entries } = dossier.data;
  const statuses = [...new Set(entries.map((e) => e.status))];
  const visible = filter === "all" ? entries : entries.filter((e) => e.status === filter);

  return (
    <div className="space-y-6">
      <PageHeader
        title="Dossiê do projeto"
        subtitle={
          <span className="flex flex-wrap items-center gap-2">
            {project.name} {project.is_synthetic && <SyntheticBadge />}
          </span>
        }
      />
      <Alert>
        <AlertTitle>O Basho não decide enquadramento</AlertTitle>
        <AlertDescription>
          Este dossiê organiza evidências e decisões humanas. Não garante benefício fiscal nem substitui a análise dos
          responsáveis: os itens são potencialmente qualificáveis, sujeitos a análise.
        </AlertDescription>
      </Alert>

      <div className="flex flex-wrap items-center gap-1" role="group" aria-label="Filtrar por estado">
        <Button size="sm" variant={filter === "all" ? "default" : "outline"} aria-pressed={filter === "all"} onClick={() => setFilter("all")}>
          Todos ({entries.length})
        </Button>
        {statuses.map((status) => (
          <Button
            key={status}
            size="sm"
            variant={filter === status ? "default" : "outline"}
            aria-pressed={filter === status}
            onClick={() => setFilter(status)}
          >
            <ArtifactStatusBadge status={status} />
          </Button>
        ))}
      </div>

      <Section title="Registros">
        {visible.length === 0 ? (
          <EmptyState title="Nenhum registro neste filtro." />
        ) : (
          <div className="space-y-4">
            {visible.map((entry) => (
              <EntryCard key={entry.artifact_id} entry={entry} />
            ))}
          </div>
        )}
      </Section>
    </div>
  );
}
