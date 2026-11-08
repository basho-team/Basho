"use client";
import { useState, type FormEvent } from "react";
import { Pencil, FolderOpen, GitBranch, FileText } from "lucide-react";
import { useApp } from "@/store/AppContext";
import { completeness } from "@/services/simulationService";
import { saveProject } from "@/services/settingsService";
import { PageContainer } from "@/components/shared/PageContainer";
import {
  Intro,
  Field,
  NativeSelect,
  Modal,
  Notice,
  GoLink,
  Submit,
  Empty,
} from "@/components/shared/WorkspaceUI";
import { StatusBadge } from "@/components/shared/StatusBadge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Progress } from "@/components/ui/progress";
import {
  formatDate,
  formatDateShort,
  CATEGORY_LABELS,
} from "@/components/shared/helpers";
import type { ProjectStatus } from "@/types";
export default function ProjectModule({ projectId }: { projectId: string }) {
  const { state, transact } = useApp();
  const [editing, setEditing] = useState(false);
  const project = state.projects.find((p) => p.id === projectId);
  if (!project)
    return (
      <PageContainer>
        <Empty text="Projeto não encontrado." />
        <GoLink href="/projetos">Voltar aos projetos</GoLink>
      </PageContainer>
    );
  const activities = state.activities.filter((a) => a.projectId === projectId),
    docs = state.driveItems.filter(
      (d) => d.projectId === projectId && d.type === "file",
    ),
    repos = state.githubRepos.filter((r) => r.projectId === projectId),
    evidence = state.evidence.filter((e) => e.projectId === projectId),
    items = state.leiDoBemItems.filter((i) => i.projectId === projectId),
    approvals = state.approvalRequests.filter(
      (a) =>
        a.projectId === projectId &&
        ["pending", "needs_revision"].includes(a.status),
    );
  function save(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const form = new FormData(e.currentTarget);
    if (
      transact(
        (s) =>
          saveProject(s, projectId, {
            name: String(form.get("name")),
            description: String(form.get("description")),
            objectives: String(form.get("objectives")),
            responsible: String(form.get("responsible")),
            startDate: String(form.get("startDate")),
            endDate: String(form.get("endDate")),
            status: String(form.get("status")) as ProjectStatus,
          }),
        "Projeto atualizado",
      )
    )
      setEditing(false);
  }
  return (
    <PageContainer>
      <GoLink href="/projetos">Todos os projetos</GoLink>
      <Intro
        eyebrow={project.identifier}
        title={project.name}
        description={project.description}
      >
        <Button variant="outline" onClick={() => setEditing(true)}>
          <Pencil className="mr-2 h-4 w-4" />
          Editar projeto
        </Button>
      </Intro>
      <div className="flex flex-wrap items-center gap-4 text-sm">
        <StatusBadge status={project.status} />
        <span>
          {formatDateShort(project.startDate)} —{" "}
          {formatDateShort(project.endDate)}
        </span>
        <span>Responsável: {project.responsible}</span>
      </div>
      <Card>
        <CardContent className="grid gap-6 pt-6 md:grid-cols-[1fr_280px]">
          <div>
            <h3 className="mb-2 font-semibold">Objetivos técnicos</h3>
            <p className="text-sm leading-relaxed text-muted-foreground">
              {project.objectives}
            </p>
            <p className="mt-4 text-xs text-muted-foreground">
              Equipe: {project.team.join(" · ")}
            </p>
          </div>
          <div className="space-y-3">
            <div className="flex justify-between text-sm">
              <span>Completude documental</span>
              <strong>{completeness(state, projectId)}%</strong>
            </div>
            <Progress value={completeness(state, projectId)} />
            <GoLink href="/lei-do-bem">Revisar checklist documental</GoLink>
            <p className="text-xs text-muted-foreground">
              Presença documental, sujeita a análise dos responsáveis.
            </p>
          </div>
        </CardContent>
      </Card>
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        {[
          ["Atividades", activities.length],
          ["Documentos", docs.length],
          ["Evidências", evidence.length],
          ["Decisões pendentes", approvals.length],
        ].map(([label, count]) => (
          <Card key={label}>
            <CardContent className="pt-5">
              <p className="text-2xl font-semibold">{count}</p>
              <p className="mt-1 text-xs text-muted-foreground">{label}</p>
            </CardContent>
          </Card>
        ))}
      </div>
      <div className="grid gap-5 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Atividades e execução</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            {activities.map((a) => (
              <div
                key={a.id}
                className="flex items-start justify-between gap-3 border-b pb-3"
              >
                <div>
                  <p className="text-sm font-medium">{a.title}</p>
                  <p className="mt-1 text-xs text-muted-foreground">
                    {a.assignee} · {a.evidenceIds.length} evidências ·{" "}
                    {formatDateShort(a.dueDate)}
                  </p>
                </div>
                <StatusBadge status={a.status} />
              </div>
            ))}
            <GoLink href="/atividades">Gerenciar atividades</GoLink>
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>Repositórios e diretórios</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            {repos.map((repo) => (
              <div key={repo.id} className="flex items-center gap-3 text-sm">
                <GitBranch className="h-4 w-4 text-emerald-700" />
                {repo.fullName}
                <span className="ml-auto text-xs text-muted-foreground">
                  {
                    state.githubEvents.filter((e) => e.repoId === repo.id)
                      .length
                  }{" "}
                  eventos
                </span>
              </div>
            ))}
            {state.driveItems
              .filter((d) => d.type === "folder" && d.projectId === projectId)
              .map((folder) => (
                <div
                  key={folder.id}
                  className="flex items-center gap-3 text-sm"
                >
                  <FolderOpen className="h-4 w-4 text-muted-foreground" />
                  {folder.name}
                </div>
              ))}
            <div className="flex flex-wrap gap-4">
              <GoLink href="/integracoes">Configurar fontes</GoLink>
              <GoLink href={`/documentos?projeto=${projectId}`}>
                Explorar documentos
              </GoLink>
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>Documentos e relatórios produzidos</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            {docs.map((doc) => (
              <div key={doc.id} className="flex gap-3 border-b pb-3">
                <FileText className="mt-1 h-4 w-4 shrink-0 text-muted-foreground" />
                <div>
                  <GoLink href={`/documentos?arquivo=${doc.id}`}>
                    {doc.name}
                  </GoLink>
                  <p className="mt-1 text-xs text-muted-foreground">
                    {CATEGORY_LABELS[doc.category ?? ""]} ·{" "}
                    {doc.isOriginal ? "Original preservado" : "Derivado"}
                  </p>
                </div>
              </div>
            ))}
            {!docs.length && (
              <Empty text="Ainda não há documentos neste projeto." />
            )}
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>Pendências e evidências técnicas</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <Notice>
              {
                items.filter((i) =>
                  ["absent", "draft", "pending_review"].includes(i.status),
                ).length
              }{" "}
              itens documentais ainda exigem elaboração ou revisão.
            </Notice>
            {project.pendingItems.map((item, index) => (
              <p
                key={index}
                className="border-l-2 border-amber-400 pl-3 text-sm text-muted-foreground"
              >
                {item}
              </p>
            ))}
            {evidence.map((ev) => (
              <details key={ev.id} className="border-t pt-3 text-sm">
                <summary>{ev.claim}</summary>
                <p className="mt-2 text-xs text-muted-foreground">
                  {ev.reason} · Fonte: {ev.sourceRef}
                </p>
              </details>
            ))}
            {approvals.length > 0 && (
              <GoLink href="/aprovacoes">
                Revisar {approvals.length} solicitações abertas
              </GoLink>
            )}
          </CardContent>
        </Card>
      </div>
      <Card>
        <CardHeader>
          <CardTitle>Histórico do projeto</CardTitle>
        </CardHeader>
        <CardContent>
          {[...project.history].reverse().map((h) => (
            <div key={h.id} className="border-t py-3 text-sm">
              <p>{h.action}</p>
              <p className="mt-1 text-xs text-muted-foreground">
                {h.actor} · {formatDate(h.timestamp)}
              </p>
            </div>
          ))}
        </CardContent>
      </Card>
      <Modal
        open={editing}
        onClose={() => setEditing(false)}
        title="Editar projeto de PD&I"
      >
        <form onSubmit={save} className="space-y-4">
          <Field label="Nome">
            <Input name="name" required defaultValue={project.name} />
          </Field>
          <Field label="Descrição">
            <textarea
              className="field"
              name="description"
              defaultValue={project.description}
            />
          </Field>
          <Field label="Objetivos técnicos">
            <textarea
              className="field"
              name="objectives"
              required
              defaultValue={project.objectives}
            />
          </Field>
          <Field label="Responsável">
            <Input
              name="responsible"
              required
              defaultValue={project.responsible}
            />
          </Field>
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Início">
              <Input
                type="date"
                name="startDate"
                required
                defaultValue={project.startDate}
              />
            </Field>
            <Field label="Término">
              <Input
                type="date"
                name="endDate"
                required
                defaultValue={project.endDate}
              />
            </Field>
          </div>
          <Field label="Status">
            <NativeSelect name="status" defaultValue={project.status}>
              <option value="active">Ativo</option>
              <option value="planning">Planejamento</option>
              <option value="on_hold">Suspenso</option>
              <option value="completed">Concluído</option>
              <option value="cancelled">Cancelado</option>
            </NativeSelect>
          </Field>
          <Submit />
        </form>
      </Modal>
    </PageContainer>
  );
}
