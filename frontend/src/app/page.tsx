"use client";
import Link from "next/link";
import { Intro, GoLink } from "@/components/shared/WorkspaceUI";
import { useApp } from "@/store/AppContext";
import { PageContainer } from "@/components/shared/PageContainer";
import { MetricCard } from "@/components/shared/MetricCard";
import { StatusBadge } from "@/components/shared/StatusBadge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import {
  FolderKanban,
  ListTodo,
  FileText,
  FlaskConical,
  ShieldCheck,
  Cpu,
  ArrowRight,
  AlertCircle,
} from "lucide-react";
import { formatDate, timeAgo } from "@/components/shared/helpers";

export default function DashboardPage() {
  const { state } = useApp();

  const activeProjects = state.projects.filter(
    (p) => p.status === "active",
  ).length;
  const pendingActivities = state.activities.filter(
    (a) => a.status === "in_progress",
  ).length;
  const doneActivities = state.activities.filter(
    (a) => a.status === "done",
  ).length;
  const missingDocs = state.leiDoBemItems.filter(
    (i) => i.status === "absent",
  ).length;
  const totalDocs = state.driveItems.filter((i) => i.type === "file").length;
  const totalEvidence = state.evidence.length;
  const pendingApprovals = state.approvalRequests.filter(
    (a) => a.status === "pending",
  ).length;
  const completedRuns = state.agentRuns.filter(
    (r) => r.status === "completed",
  ).length;

  const recentActivities = [...state.activities]
    .sort(
      (a, b) =>
        new Date(b.modifiedAt).getTime() - new Date(a.modifiedAt).getTime(),
    )
    .slice(0, 5);

  const recentRuns = [...state.agentRuns]
    .sort(
      (a, b) =>
        new Date(b.startedAt).getTime() - new Date(a.startedAt).getTime(),
    )
    .slice(0, 5);

  const pendingItems = state.projects.flatMap((p) =>
    p.pendingItems.map((item) => ({ project: p.identifier, item })),
  );

  return (
    <PageContainer>
      <Intro
        title="Acompanhe sua operação de PD&I"
        description="Projetos, documentação e decisões conectados em um só lugar."
      >
        <GoLink href="/operacoes">Abrir Central de Operações</GoLink>
      </Intro>
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <MetricCard
          label="Projetos ativos"
          value={activeProjects}
          icon={<FolderKanban className="h-5 w-5" />}
        />
        <MetricCard
          label="Atividades em andamento"
          value={pendingActivities}
          icon={<ListTodo className="h-5 w-5" />}
        />
        <MetricCard
          label="Atividades concluídas"
          value={doneActivities}
          icon={<ListTodo className="h-5 w-5" />}
        />
        <MetricCard
          label="Pendências documentais"
          value={missingDocs}
          icon={<AlertCircle className="h-5 w-5" />}
        />
        <MetricCard
          label="Documentos"
          value={totalDocs}
          icon={<FileText className="h-5 w-5" />}
        />
        <MetricCard
          label="Evidências"
          value={totalEvidence}
          icon={<FlaskConical className="h-5 w-5" />}
        />
        <MetricCard
          label="Aprovações pendentes"
          value={pendingApprovals}
          icon={<ShieldCheck className="h-5 w-5" />}
        />
        <MetricCard
          label="Execuções concluídas"
          value={completedRuns}
          icon={<Cpu className="h-5 w-5" />}
        />
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between">
            <CardTitle>Atividades recentes</CardTitle>
            <Link href="/atividades">
              <Button variant="ghost" size="sm" className="gap-1">
                Ver todas <ArrowRight className="h-3 w-3" />
              </Button>
            </Link>
          </CardHeader>
          <CardContent className="space-y-3">
            {recentActivities.length === 0 && (
              <p className="text-sm text-muted-foreground">
                Nenhuma atividade registrada.
              </p>
            )}
            {recentActivities.map((act) => {
              const project = state.projects.find(
                (p) => p.id === act.projectId,
              );
              return (
                <div
                  key={act.id}
                  className="flex items-center justify-between border-b pb-3 last:border-0 last:pb-0"
                >
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm font-medium">{act.title}</p>
                    <p className="text-xs text-muted-foreground">
                      {project?.identifier} · {act.assignee} ·{" "}
                      {timeAgo(act.modifiedAt)}
                    </p>
                  </div>
                  <StatusBadge status={act.status} />
                </div>
              );
            })}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between">
            <CardTitle>Execuções recentes</CardTitle>
            <Link href="/operacoes">
              <Button variant="ghost" size="sm" className="gap-1">
                Ver todas <ArrowRight className="h-3 w-3" />
              </Button>
            </Link>
          </CardHeader>
          <CardContent className="space-y-3">
            {recentRuns.length === 0 && (
              <p className="text-sm text-muted-foreground">
                Nenhuma execução registrada. Acesse a Central de Operações para
                disparar cenários.
              </p>
            )}
            {recentRuns.map((run) => (
              <div
                key={run.id}
                className="flex items-center justify-between border-b pb-3 last:border-0 last:pb-0"
              >
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm font-medium">
                    {run.triggerEvent}
                  </p>
                  <p className="text-xs text-muted-foreground">
                    {formatDate(run.startedAt)} ·{" "}
                    {run.correlationId.substring(0, 16)}
                  </p>
                </div>
                <StatusBadge status={run.status} />
              </div>
            ))}
          </CardContent>
        </Card>
      </div>

      {pendingItems.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <AlertCircle className="h-5 w-5 text-amber-500" />
              Itens pendentes dos projetos
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-2">
            {pendingItems.map((pi, idx) => (
              <div key={idx} className="flex items-start gap-3 text-sm">
                <span className="font-mono text-xs text-muted-foreground">
                  {pi.project}
                </span>
                <span className="flex-1 text-muted-foreground">{pi.item}</span>
              </div>
            ))}
          </CardContent>
        </Card>
      )}
    </PageContainer>
  );
}
