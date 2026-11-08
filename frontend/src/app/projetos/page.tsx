"use client";
import Link from "next/link";
import { Intro } from "@/components/shared/WorkspaceUI";
import { useApp } from "@/store/AppContext";
import { PageContainer } from "@/components/shared/PageContainer";
import { StatusBadge } from "@/components/shared/StatusBadge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { ArrowRight } from "lucide-react";
import { formatDateShort } from "@/components/shared/helpers";

export default function ProjectsPage() {
  const { state } = useApp();

  return (
    <PageContainer>
      <Intro
        title="Projetos de PD&I"
        description="Contexto técnico, atividades e documentação reunidos por projeto."
      />
      <div className="grid gap-4 md:grid-cols-2">
        {state.projects.map((project) => {
          const activities = state.activities.filter(
            (a) => a.projectId === project.id,
          );
          const repos = state.githubRepos.filter(
            (r) => r.projectId === project.id,
          );
          const evidence = state.evidence.filter(
            (e) => e.projectId === project.id,
          );
          const docs = state.driveItems.filter(
            (d) => d.projectId === project.id && d.type === "file",
          );

          return (
            <Card
              key={project.id}
              className="transition-shadow hover:shadow-md"
            >
              <CardHeader>
                <div className="flex items-start justify-between">
                  <div>
                    <div className="flex items-center gap-2">
                      <span className="font-mono text-sm text-muted-foreground">
                        {project.identifier}
                      </span>
                      <StatusBadge status={project.status} />
                    </div>
                    <CardTitle className="mt-1">{project.name}</CardTitle>
                  </div>
                  <Link
                    aria-label={`Abrir projeto ${project.identifier}`}
                    href={`/projetos/${project.id}`}
                  >
                    <ArrowRight className="h-4 w-4 text-muted-foreground hover:text-foreground" />
                  </Link>
                </div>
              </CardHeader>
              <CardContent className="space-y-4">
                <p className="line-clamp-2 text-sm text-muted-foreground">
                  {project.description}
                </p>

                <div className="space-y-1">
                  <div className="flex justify-between text-xs text-muted-foreground">
                    <span>Completude</span>
                    <span>{project.completeness}%</span>
                  </div>
                  <Progress value={project.completeness} className="h-2" />
                </div>

                <div className="grid grid-cols-4 gap-2 text-center">
                  <div className="rounded-lg bg-muted/50 p-2">
                    <p className="text-lg font-bold">{activities.length}</p>
                    <p className="text-xs text-muted-foreground">Atividades</p>
                  </div>
                  <div className="rounded-lg bg-muted/50 p-2">
                    <p className="text-lg font-bold">{docs.length}</p>
                    <p className="text-xs text-muted-foreground">Documentos</p>
                  </div>
                  <div className="rounded-lg bg-muted/50 p-2">
                    <p className="text-lg font-bold">{evidence.length}</p>
                    <p className="text-xs text-muted-foreground">Evidências</p>
                  </div>
                  <div className="rounded-lg bg-muted/50 p-2">
                    <p className="text-lg font-bold">{repos.length}</p>
                    <p className="text-xs text-muted-foreground">
                      Repositórios
                    </p>
                  </div>
                </div>

                <div className="flex items-center justify-between text-xs text-muted-foreground">
                  <span>Responsável: {project.responsible}</span>
                  <span>
                    {formatDateShort(project.startDate)} —{" "}
                    {formatDateShort(project.endDate)}
                  </span>
                </div>

                {project.pendingItems.length > 0 && (
                  <div className="rounded-lg border border-amber-500/20 bg-amber-500/5 p-3">
                    <p className="mb-1 text-xs font-semibold text-amber-700">
                      Pendências ({project.pendingItems.length})
                    </p>
                    <ul className="space-y-1">
                      {project.pendingItems.slice(0, 2).map((item, i) => (
                        <li key={i} className="text-xs text-muted-foreground">
                          • {item}
                        </li>
                      ))}
                      {project.pendingItems.length > 2 && (
                        <li className="text-xs text-muted-foreground">
                          + {project.pendingItems.length - 2} mais...
                        </li>
                      )}
                    </ul>
                  </div>
                )}
              </CardContent>
            </Card>
          );
        })}
      </div>
    </PageContainer>
  );
}
