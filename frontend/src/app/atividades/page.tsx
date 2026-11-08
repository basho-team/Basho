"use client";
import { useState, type FormEvent } from "react";
import { Plus, List, Columns3 } from "lucide-react";
import { useApp } from "@/store/AppContext";
import { PageContainer } from "@/components/shared/PageContainer";
import {
  Intro,
  Field,
  NativeSelect,
  Modal,
  SearchBox,
  Empty,
  Notice,
  Submit,
} from "@/components/shared/WorkspaceUI";
import { StatusBadge } from "@/components/shared/StatusBadge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import {
  PRIORITY_LABELS,
  ORIGIN_LABELS,
  formatDate,
  formatDateShort,
  getProjectIdentifier,
} from "@/components/shared/helpers";
import { timestamp, uid } from "@/services/simulationService";
import type { Activity, ActivityPriority, ActivityStatus } from "@/types";
const COLUMNS: Array<[ActivityStatus, string]> = [
  ["todo", "A fazer"],
  ["in_progress", "Em andamento"],
  ["review", "Em revisão"],
  ["done", "Concluídas"],
  ["blocked", "Bloqueadas"],
];
export default function ActivitiesPage() {
  const { state, execute } = useApp();
  const [view, setView] = useState<"kanban" | "table">("kanban"),
    [query, setQuery] = useState(""),
    [project, setProject] = useState("");
  const [editing, setEditing] = useState<Activity | null | undefined>(
    undefined,
  );
  const [formProject, setFormProject] = useState(state.projects[0].id);
  const rows = state.activities.filter(
    (a) =>
      (!project || a.projectId === project) &&
      `${a.title} ${a.assignee} ${a.id}`
        .toLowerCase()
        .includes(query.toLowerCase()),
  );
  function open(activity: Activity | null) {
    setEditing(activity);
    setFormProject(activity?.projectId ?? state.projects[0].id);
  }
  function save(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const data = new FormData(e.currentTarget),
      now = timestamp();
    const values = {
      title: String(data.get("title")).trim(),
      description: String(data.get("description") ?? ""),
      assignee: String(data.get("assignee") ?? "").trim(),
      priority: String(data.get("priority")) as ActivityPriority,
      status: String(data.get("status")) as ActivityStatus,
      dueDate: String(data.get("dueDate") ?? "") || null,
      evidenceIds: data.getAll("evidence").map(String),
    };
    let accepted;
    if (editing) {
      const patch: typeof values = { ...values };
      for (const key of Object.keys(patch) as Array<keyof typeof values>)
        if (JSON.stringify(patch[key]) === JSON.stringify(editing[key]))
          delete patch[key];
      accepted = execute({ kind: "activity.update", id: editing.id, patch });
    } else
      accepted = execute({
        kind: "activity.create",
        activity: {
          ...values,
          id: uid("activity"),
          projectId: formProject,
          origin: "user",
          history: [
            {
              id: uid("hist"),
              timestamp: now,
              actor: "Operador",
              action: "Atividade criada",
            },
          ],
          createdAt: now,
          modifiedAt: now,
          isSynthetic: true,
        },
      });
    if (accepted) setEditing(undefined);
  }
  return (
    <PageContainer>
      <Intro
        eyebrow="NOTION SIMULADO"
        title="Do planejamento à evidência"
        description="Acompanhe a execução e mantenha o contexto técnico de cada atividade."
      >
        <Button onClick={() => open(null)}>
          <Plus className="mr-2 h-4 w-4" />
          Nova atividade
        </Button>
      </Intro>
      <div className="flex flex-wrap gap-3">
        <SearchBox
          value={query}
          onChange={setQuery}
          placeholder="Pesquisar atividade ou responsável…"
        />
        <NativeSelect
          aria-label="Projeto das atividades"
          className="sm:max-w-52"
          value={project}
          onChange={(e) => setProject(e.target.value)}
        >
          <option value="">Todos os projetos</option>
          {state.projects.map((p) => (
            <option key={p.id} value={p.id}>
              {p.identifier}
            </option>
          ))}
        </NativeSelect>
        <Button
          aria-pressed={view === "kanban"}
          variant={view === "kanban" ? "default" : "outline"}
          onClick={() => setView("kanban")}
        >
          <Columns3 className="mr-2 h-4 w-4" />
          Kanban
        </Button>
        <Button
          aria-pressed={view === "table"}
          variant={view === "table" ? "default" : "outline"}
          onClick={() => setView("table")}
        >
          <List className="mr-2 h-4 w-4" />
          Tabela
        </Button>
      </div>
      <Notice>
        Alterações obedecem à autonomia configurada. Concluir atividades, por
        padrão, prepara uma solicitação de aprovação.
      </Notice>
      {view === "kanban" ? (
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-5">
          {COLUMNS.map(([status, label]) => (
            <section
              key={status}
              className="min-w-0 rounded-xl border bg-muted/30 p-3"
            >
              <h3 className="mb-4 flex justify-between px-1 text-sm font-semibold">
                {label}
                <span className="text-muted-foreground">
                  {rows.filter((a) => a.status === status).length}
                </span>
              </h3>
              <div className="space-y-3">
                {rows
                  .filter((a) => a.status === status)
                  .map((a) => (
                    <Card key={a.id} className="space-y-3 p-4">
                      <p className="font-mono text-[10px] text-muted-foreground">
                        {getProjectIdentifier(state, a.projectId)} ·{" "}
                        {a.id.slice(0, 12)}
                      </p>
                      <button
                        className="text-left text-sm font-semibold hover:text-emerald-800"
                        onClick={() => open(a)}
                      >
                        {a.title}
                      </button>
                      <p className="text-xs text-muted-foreground">
                        {a.assignee} · {PRIORITY_LABELS[a.priority]}
                      </p>
                      <p className="text-xs text-muted-foreground">
                        {a.evidenceIds.length} evidência(s) ·{" "}
                        {formatDateShort(a.dueDate)}
                      </p>
                      <NativeSelect
                        aria-label={`Status de ${a.title}`}
                        className="text-xs"
                        value={a.status}
                        onChange={(e) =>
                          execute({
                            kind: "activity.update",
                            id: a.id,
                            patch: { status: e.target.value as ActivityStatus },
                          })
                        }
                      >
                        {COLUMNS.map(([id, name]) => (
                          <option key={id} value={id}>
                            {name}
                          </option>
                        ))}
                      </NativeSelect>
                    </Card>
                  ))}
              </div>
            </section>
          ))}
        </div>
      ) : (
        <Card className="overflow-x-auto">
          <table className="data-table">
            <thead>
              <tr>
                <th>Atividade</th>
                <th>Responsável / prazo</th>
                <th>Prioridade</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((a) => (
                <tr key={a.id}>
                  <td>
                    <button
                      onClick={() => open(a)}
                      className="text-left font-medium hover:underline"
                    >
                      {a.title}
                    </button>
                    <p className="mt-1 text-xs text-muted-foreground">
                      {getProjectIdentifier(state, a.projectId)} ·{" "}
                      {ORIGIN_LABELS[a.origin]} · {a.evidenceIds.length}{" "}
                      evidências
                    </p>
                  </td>
                  <td>
                    {a.assignee}
                    <p className="text-xs text-muted-foreground">
                      {formatDateShort(a.dueDate)}
                    </p>
                  </td>
                  <td>{PRIORITY_LABELS[a.priority]}</td>
                  <td>
                    <StatusBadge status={a.status} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      )}
      {!rows.length && (
        <Empty text="Nenhuma atividade corresponde aos filtros." />
      )}
      <Modal
        title={editing ? "Detalhes da atividade" : "Nova atividade"}
        open={editing !== undefined}
        onClose={() => setEditing(undefined)}
      >
        {editing !== undefined && (
          <form onSubmit={save} className="space-y-4">
            <Field label="Título">
              <Input
                name="title"
                required
                maxLength={200}
                defaultValue={editing?.title}
              />
            </Field>
            <Field label="Descrição">
              <textarea
                className="field"
                name="description"
                defaultValue={editing?.description}
              />
            </Field>
            <div className="grid gap-4 sm:grid-cols-2">
              <Field label="Projeto">
                <NativeSelect
                  name="project"
                  value={formProject}
                  disabled={!!editing}
                  onChange={(e) => setFormProject(e.target.value)}
                >
                  {state.projects.map((p) => (
                    <option key={p.id} value={p.id}>
                      {p.identifier}
                    </option>
                  ))}
                </NativeSelect>
              </Field>
              <Field label="Responsável">
                <Input
                  name="assignee"
                  required
                  defaultValue={
                    editing?.assignee ??
                    state.projects.find((p) => p.id === formProject)
                      ?.responsible
                  }
                />
              </Field>
              <Field label="Prioridade">
                <NativeSelect
                  name="priority"
                  defaultValue={editing?.priority ?? "medium"}
                >
                  {Object.entries(PRIORITY_LABELS).map(([id, label]) => (
                    <option key={id} value={id}>
                      {label}
                    </option>
                  ))}
                </NativeSelect>
              </Field>
              <Field label="Status">
                <NativeSelect
                  name="status"
                  defaultValue={editing?.status ?? "todo"}
                >
                  {COLUMNS.map(([id, label]) => (
                    <option key={id} value={id}>
                      {label}
                    </option>
                  ))}
                </NativeSelect>
              </Field>
              <Field label="Prazo">
                <Input
                  type="date"
                  name="dueDate"
                  defaultValue={editing?.dueDate?.slice(0, 10)}
                />
              </Field>
            </div>
            <Field label="Evidências vinculadas">
              <NativeSelect
                name="evidence"
                multiple
                defaultValue={editing?.evidenceIds ?? []}
                size={3}
              >
                {state.evidence
                  .filter((ev) => ev.projectId === formProject)
                  .map((ev) => (
                    <option key={ev.id} value={ev.id}>
                      {ev.claim}
                    </option>
                  ))}
              </NativeSelect>
            </Field>
            {editing && (
              <details className="text-sm">
                <summary>
                  Identificação e histórico · {editing.history.length} registros
                </summary>
                <p className="my-3 break-all text-xs text-muted-foreground">
                  ID: {editing.id} · Origem: {ORIGIN_LABELS[editing.origin]}
                </p>
                {editing.history.map((h) => (
                  <div key={h.id} className="border-t py-2 text-xs">
                    <p>
                      {h.action} · {h.actor} · {formatDate(h.timestamp)}
                    </p>
                    {h.newValue && (
                      <pre className="mt-2 max-h-32 overflow-auto whitespace-pre-wrap text-muted-foreground">
                        {h.newValue}
                      </pre>
                    )}
                  </div>
                ))}
              </details>
            )}
            <Submit />
          </form>
        )}
      </Modal>
    </PageContainer>
  );
}
