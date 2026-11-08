"use client";
import { useState } from "react";
import {
  Play,
  GitPullRequest,
  FolderSync,
  ShieldAlert,
  RotateCcw,
  Check,
  ArrowRight,
} from "lucide-react";
import { useApp } from "@/store/AppContext";
import { useWorkflow } from "@/hooks/useWorkflow";
import { SCENARIOS, retryRun } from "@/services/workflowEngine";
import { PageContainer } from "@/components/shared/PageContainer";
import {
  Intro,
  NativeSelect,
  Empty,
  Notice,
  GoLink,
} from "@/components/shared/WorkspaceUI";
import { StatusBadge } from "@/components/shared/StatusBadge";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import {
  MODULE_LABELS,
  formatDate,
  getProjectIdentifier,
} from "@/components/shared/helpers";
const ICONS = { A: GitPullRequest, B: FolderSync, C: ShieldAlert };
export default function OperationsPage() {
  const { state, transact } = useApp();
  const { triggerScenario } = useWorkflow();
  const [project, setProject] = useState(state.projects[0].id),
    [filter, setFilter] = useState(""),
    [original, setOriginal] = useState(true);
  const runs = state.agentRuns.filter((r) => !filter || r.status === filter);
  return (
    <PageContainer>
      <Intro
        eyebrow="ORQUESTRAÇÃO DETERMINÍSTICA"
        title="Central de Operações"
        description="Do evento ao resultado: acompanhe cada etapa, ferramenta, decisão e evidência."
      />
      <Notice>
        Ambiente de demonstração · módulos simulados, sem IA real. Conecte as
        integrações em <GoLink href="/integracoes">Integrações</GoLink>. Etapas
        bloqueadas podem ser retomadas após corrigir a configuração.
      </Notice>
      <div className="flex flex-wrap items-center gap-3">
        <label htmlFor="scenario-project" className="text-sm font-medium">
          Projeto da simulação
        </label>
        <NativeSelect
          id="scenario-project"
          className="sm:max-w-72"
          value={project}
          onChange={(e) => setProject(e.target.value)}
        >
          {state.projects.map((p) => (
            <option key={p.id} value={p.id}>
              {p.identifier} — {p.name}
            </option>
          ))}
        </NativeSelect>
        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={original}
            onChange={(e) => setOriginal(e.target.checked)}
          />
          Cenário B com documento original protegido
        </label>
      </div>
      <div className="grid gap-4 md:grid-cols-3">
        {SCENARIOS.map((s) => {
          const Icon = ICONS[s.id];
          return (
            <Card key={s.id}>
              <CardContent className="space-y-4 pt-6">
                <div className="flex items-center justify-between">
                  <Icon className="h-6 w-6 text-emerald-700" />
                  <span className="font-mono text-xs text-muted-foreground">
                    CENÁRIO {s.id}
                  </span>
                </div>
                <h3 className="font-semibold">{s.title}</h3>
                <p className="min-h-10 text-sm text-muted-foreground">
                  {s.description}
                </p>
                <Button
                  className="w-full"
                  variant="outline"
                  onClick={() => triggerScenario(s.id, project, original)}
                >
                  <Play className="mr-2 h-3.5 w-3.5" />
                  {s.triggerLabel}
                </Button>
              </CardContent>
            </Card>
          );
        })}
      </div>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h3 className="text-lg font-semibold">
          Execuções{" "}
          <span className="text-muted-foreground">({runs.length})</span>
        </h3>
        <NativeSelect
          className="sm:max-w-60"
          aria-label="Filtrar execuções por estado"
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
        >
          <option value="">Todos os estados</option>
          <option value="running">Em execução</option>
          <option value="completed">Concluído</option>
          <option value="awaiting_approval">Aguardando aprovação</option>
          <option value="blocked_by_policy">Bloqueado por política</option>
          <option value="failed">Falhou</option>
          <option value="waiting">Aguardando</option>
        </NativeSelect>
      </div>
      {runs.map((run) => (
        <Card key={run.id} className="overflow-hidden">
          <details
            open={
              run.status === "running" ||
              run.status === "awaiting_approval" ||
              run.status === "blocked_by_policy"
            }
          >
            <summary className="flex flex-wrap items-center justify-between gap-4 p-5">
              <div className="min-w-0 flex-1">
                <p className="text-sm font-semibold">{run.triggerEvent}</p>
                <p className="mt-2 text-xs text-muted-foreground">
                  {MODULE_LABELS[run.module]} ·{" "}
                  {getProjectIdentifier(state, run.projectId)} ·{" "}
                  {formatDate(run.startedAt)}
                </p>
              </div>
              <StatusBadge status={run.status} />
              <ArrowRight className="h-4 w-4" />
            </summary>
            <div className="border-t p-5">
              <p className="mb-4 break-all font-mono text-[10px] text-muted-foreground">
                Execução {run.id} · origem {run.triggerSource} · correlação{" "}
                {run.correlationId}
              </p>
              <ol className="space-y-1">
                {run.steps.map((step) => (
                  <li key={step.id} className="flex gap-3">
                    <div className="flex flex-col items-center">
                      <span
                        className={`grid h-7 w-7 shrink-0 place-items-center rounded-full text-xs ${step.status === "completed" ? "bg-emerald-100 text-emerald-800" : "bg-muted text-muted-foreground"}`}
                      >
                        {step.status === "completed" ? (
                          <Check className="h-3.5 w-3.5" />
                        ) : (
                          step.sequence
                        )}
                      </span>
                      <div className="min-h-6 w-px flex-1 bg-border" />
                    </div>
                    <div className="min-w-0 flex-1 pb-5">
                      <div className="flex flex-wrap items-center justify-between gap-2">
                        <p className="text-sm font-medium">{step.label}</p>
                        <StatusBadge status={step.status} />
                      </div>
                      <p className="mt-1 text-xs text-muted-foreground">
                        Ferramenta: {step.tool ?? "orquestrador"} ·{" "}
                        {formatDate(step.timestamp)}
                      </p>
                      {step.result && (
                        <p className="mt-2 text-sm text-muted-foreground">
                          {step.result}
                        </p>
                      )}
                      {step.command && (
                        <details className="mt-2 text-xs text-muted-foreground">
                          <summary>Plano e recurso afetado</summary>
                          <pre className="mt-2 max-h-48 overflow-auto whitespace-pre-wrap rounded bg-muted p-3">
                            {JSON.stringify(step.command, null, 2)}
                          </pre>
                        </details>
                      )}
                    </div>
                  </li>
                ))}
              </ol>
              <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg bg-muted/50 p-4">
                <p className="text-sm">
                  {run.error ?? run.result ?? "Executando etapas planejadas…"}
                </p>
                {run.status === "blocked_by_policy" && (
                  <Button
                    size="sm"
                    onClick={() =>
                      transact(
                        (s) => retryRun(s, run.id),
                        "Revalidando a etapa bloqueada",
                      )
                    }
                  >
                    <RotateCcw className="mr-2 h-3 w-3" />
                    Retomar após ajuste
                  </Button>
                )}
                {run.status === "awaiting_approval" && (
                  <GoLink href="/aprovacoes">Revisar decisão pendente</GoLink>
                )}
              </div>
              <div className="mt-4 flex flex-wrap gap-5">
                <GoLink href={`/documentos?projeto=${run.projectId}`}>
                  Documentos produzidos
                </GoLink>
                <GoLink href="/atividades">Atividades</GoLink>
                <GoLink href={`/auditoria?execucao=${run.id}`}>
                  Auditoria da execução
                </GoLink>
              </div>
            </div>
          </details>
        </Card>
      ))}
      {!runs.length && (
        <Empty text="Dispare um cenário para acompanhar sua primeira execução." />
      )}
    </PageContainer>
  );
}
