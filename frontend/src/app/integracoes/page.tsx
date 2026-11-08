"use client";
import { useState, type FormEvent } from "react";
import {
  GitBranch,
  FolderOpen,
  NotebookPen,
  Plug,
  Settings2,
  CheckCircle2,
  Zap,
} from "lucide-react";
import { useApp } from "@/store/AppContext";
import { useWorkflow } from "@/hooks/useWorkflow";
import {
  defaultConfig,
  linkRepo,
  saveIntegration,
} from "@/services/settingsService";
import { timestamp, uid } from "@/services/simulationService";
import { PageContainer } from "@/components/shared/PageContainer";
import {
  Intro,
  Field,
  NativeSelect,
  Notice,
  GoLink,
  Submit,
  Empty,
} from "@/components/shared/WorkspaceUI";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import {
  formatDate,
  getProjectIdentifier,
  getRepoName,
} from "@/components/shared/helpers";
import type { GithubEventType, Integration, IntegrationConfig } from "@/types";
export const EVENT_LABELS: Record<GithubEventType, string> = {
  commit: "Novo commit",
  pr_merged: "Pull request integrado",
  pr_opened: "Pull request aberto",
  issue_opened: "Issue criada",
  issue_closed: "Issue encerrada",
  ci_passed: "CI concluído",
  ci_failed: "CI falhou",
  release: "Nova release",
};
const ICONS = {
  google_drive: FolderOpen,
  notion: NotebookPen,
  github: GitBranch,
};
function IntegrationSettings({ integration }: { integration: Integration }) {
  const { state, transact, execute } = useApp();
  const { triggerGithubEvent } = useWorkflow();
  const [eventType, setEventType] = useState<GithubEventType>("pr_merged"),
    [repoId, setRepoId] = useState(state.githubRepos[0].id);
  const config = {
    ...defaultConfig(integration.provider),
    ...integration.config,
  };
  const folders = state.driveItems.filter((d) => d.type === "folder");
  function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    let next: IntegrationConfig;
    if (integration.provider === "google_drive")
      next = {
        rootFolderUrl: String(form.get("rootFolderUrl")),
        agentWorkFolderId: String(form.get("agentWorkFolderId")),
        readableFolderIds: form.getAll("read").map(String),
        writableFolderIds: form.getAll("write").map(String),
        autoOrganizeFolderIds: form.getAll("organize").map(String),
      };
    else if (integration.provider === "notion")
      next = {
        workspaceId: String(form.get("workspace")),
        databaseId: String(form.get("database")),
        databaseName:
          form.get("database") === "database-activities"
            ? "Atividades de PD&I"
            : "Experimentos e testes",
        allowCreateTasks: form.has("create"),
        allowEditTasks: form.has("edit"),
      };
    else
      next = {
        installationId: "app-demo",
        orgOrUser: String(form.get("org")),
        monitoredRepoIds: form.getAll("repos").map(String),
        eventTriggers: form.getAll("triggers").map(String),
      };
    transact(
      (s) => saveIntegration(s, integration.id, { config: next }),
      "Configuração da integração simulada salva",
    );
  }
  function sync() {
    const id = "notion-synced-activity",
      existing = state.activities.find((a) => a.id === id);
    if (existing)
      execute({
        kind: "activity.update",
        id,
        patch: {
          description: `Atividade sincronizada da base fictícia ${config.databaseName}. Sincronização: ${timestamp()}`,
        },
      });
    else
      execute({
        kind: "activity.create",
        activity: {
          id,
          externalId: "external-demo-001",
          title: "Revisar protocolo experimental importado",
          description:
            "Atividade sintética recebida da base Notion configurada.",
          projectId: state.projects[0].id,
          assignee: state.projects[0].responsible,
          status: "todo",
          priority: "medium",
          dueDate: null,
          evidenceIds: [],
          origin: "system",
          history: [
            {
              id: uid("hist"),
              timestamp: timestamp(),
              actor: "Notion simulado",
              action: "Sincronização de atividade",
            },
          ],
          createdAt: timestamp(),
          modifiedAt: timestamp(),
          isSynthetic: true,
        },
      });
  }
  return (
    <div className="space-y-5">
      <Card>
        <CardHeader>
          <CardTitle>Configuração · {integration.label}</CardTitle>
          <p className="text-sm text-muted-foreground">
            Escopo autorizado para os módulos simulados. Salve para aplicar.
          </p>
        </CardHeader>
        <CardContent>
          <form onSubmit={save} className="space-y-5">
            {integration.provider === "google_drive" && (
              <>
                <Field label="Link da pasta principal">
                  <Input
                    name="rootFolderUrl"
                    required
                    defaultValue={config.rootFolderUrl}
                  />
                </Field>
                <Field label="Pasta de trabalho dos agentes">
                  <NativeSelect
                    name="agentWorkFolderId"
                    defaultValue={config.agentWorkFolderId}
                  >
                    {folders.map((f) => (
                      <option key={f.id} value={f.id}>
                        {f.name}
                      </option>
                    ))}
                  </NativeSelect>
                </Field>
                <div className="overflow-x-auto">
                  <table className="data-table">
                    <caption>
                      Diretórios autorizados · a seleção inclui subpastas
                    </caption>
                    <thead>
                      <tr>
                        <th>Diretório</th>
                        <th>Leitura</th>
                        <th>Escrita</th>
                        <th>Reorganizar derivados</th>
                      </tr>
                    </thead>
                    <tbody>
                      {folders.map((folder) => (
                        <tr key={folder.id}>
                          <td>
                            {folder.name}
                            <p className="text-xs text-muted-foreground">
                              {state.driveItems.find(
                                (d) => d.id === folder.parentId,
                              )?.name ?? "Pasta principal"}
                            </p>
                          </td>
                          {[
                            ["read", config.readableFolderIds],
                            ["write", config.writableFolderIds],
                            ["organize", config.autoOrganizeFolderIds],
                          ].map(([name, selected]) => (
                            <td key={String(name)}>
                              <input
                                aria-label={`${name}: ${folder.name}`}
                                type="checkbox"
                                name={String(name)}
                                value={folder.id}
                                defaultChecked={
                                  Array.isArray(selected) &&
                                  selected.includes(folder.id)
                                }
                              />
                            </td>
                          ))}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                <GoLink href="/documentos">
                  Abrir gerenciador de arquivos
                </GoLink>
              </>
            )}
            {integration.provider === "notion" && (
              <>
                <Field label="Workspace fictício">
                  <NativeSelect
                    name="workspace"
                    defaultValue={config.workspaceId}
                  >
                    <option value="workspace-basho-demo">
                      Basho · demonstração
                    </option>
                    <option value="workspace-lab-demo">
                      Laboratório · demonstração
                    </option>
                  </NativeSelect>
                </Field>
                <Field label="Página / database de atividades">
                  <NativeSelect
                    name="database"
                    defaultValue={config.databaseId}
                  >
                    <option value="database-activities">
                      Página PD&I / Atividades de PD&I
                    </option>
                    <option value="database-experiments">
                      Página Laboratório / Experimentos e testes
                    </option>
                  </NativeSelect>
                </Field>
                <div className="flex flex-wrap gap-5">
                  <label className="flex items-center gap-2 text-sm">
                    <input
                      type="checkbox"
                      name="create"
                      defaultChecked={config.allowCreateTasks}
                    />
                    Permitir criação
                  </label>
                  <label className="flex items-center gap-2 text-sm">
                    <input
                      type="checkbox"
                      name="edit"
                      defaultChecked={config.allowEditTasks}
                    />
                    Permitir edição
                  </label>
                </div>
                <p className="text-sm text-muted-foreground">
                  {state.projects.length} projetos e {state.activities.length}{" "}
                  atividades disponíveis na base simulada.
                </p>
                <div className="flex flex-wrap items-center gap-5">
                  <Button
                    variant="outline"
                    type="button"
                    onClick={sync}
                    disabled={integration.status !== "connected"}
                  >
                    Sincronizar atividades
                  </Button>
                  <GoLink href="/atividades">Ver atividades e histórico</GoLink>
                  <GoLink href="/projetos">Ver projetos</GoLink>
                </div>
              </>
            )}
            {integration.provider === "github" && (
              <>
                <Notice>
                  GitHub App fictícia · instalação{" "}
                  {config.installationId ?? "ainda não simulada"}. Nenhum
                  repositório real será acessado ou alterado.
                </Notice>
                <Field label="Organização / conta fictícia">
                  <NativeSelect name="org" defaultValue={config.orgOrUser}>
                    <option value="basho-tech">
                      basho-tech (organização demo)
                    </option>
                    <option value="equipe-demo">
                      equipe-demo (conta fictícia)
                    </option>
                  </NativeSelect>
                </Field>
                <fieldset className="space-y-3">
                  <legend className="mb-3 text-sm font-semibold">
                    Repositórios monitorados e projetos associados
                  </legend>
                  {state.githubRepos.map((repo) => (
                    <div
                      key={repo.id}
                      className="flex flex-wrap items-center gap-4 rounded-lg border p-3"
                    >
                      <label className="flex flex-1 items-center gap-2 text-sm">
                        <input
                          type="checkbox"
                          name="repos"
                          value={repo.id}
                          defaultChecked={config.monitoredRepoIds?.includes(
                            repo.id,
                          )}
                        />
                        {repo.fullName}
                      </label>
                      <NativeSelect
                        className="sm:max-w-44"
                        aria-label={`Projeto de ${repo.name}`}
                        value={repo.projectId ?? ""}
                        onChange={(e) =>
                          transact(
                            (s) => linkRepo(s, repo.id, e.target.value),
                            "Repositório associado ao projeto",
                          )
                        }
                      >
                        <option value="" disabled>
                          Selecione o projeto
                        </option>
                        {state.projects.map((p) => (
                          <option key={p.id} value={p.id}>
                            {p.identifier}
                          </option>
                        ))}
                      </NativeSelect>
                    </div>
                  ))}
                </fieldset>
                <fieldset>
                  <legend className="mb-3 text-sm font-semibold">
                    Eventos que iniciam workflows
                  </legend>
                  <div className="grid gap-3 sm:grid-cols-2">
                    {Object.entries(EVENT_LABELS).map(([type, label]) => (
                      <label
                        key={type}
                        className="flex items-center gap-2 text-sm"
                      >
                        <input
                          type="checkbox"
                          name="triggers"
                          value={type}
                          defaultChecked={config.eventTriggers?.includes(type)}
                        />
                        {label}
                      </label>
                    ))}
                  </div>
                </fieldset>
              </>
            )}
            <Submit />
          </form>
        </CardContent>
      </Card>
      {integration.provider === "github" && (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Zap className="h-4 w-4 text-emerald-700" />
              Feed de desenvolvimento
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="flex flex-wrap gap-3">
              <NativeSelect
                aria-label="Repositório do evento"
                className="sm:max-w-64"
                value={repoId}
                onChange={(e) => setRepoId(e.target.value)}
              >
                {state.githubRepos.map((r) => (
                  <option key={r.id} value={r.id}>
                    {r.fullName}
                  </option>
                ))}
              </NativeSelect>
              <NativeSelect
                aria-label="Tipo de evento"
                className="sm:max-w-56"
                value={eventType}
                onChange={(e) =>
                  setEventType(e.target.value as GithubEventType)
                }
              >
                {Object.entries(EVENT_LABELS).map(([id, label]) => (
                  <option key={id} value={id}>
                    {label}
                  </option>
                ))}
              </NativeSelect>
              <Button
                onClick={() => triggerGithubEvent(eventType, repoId)}
                disabled={integration.status !== "connected"}
              >
                Simular chegada
              </Button>
            </div>
            <p className="text-xs text-muted-foreground">
              PR integrado inicia o cenário A; CI com falha inicia o cenário C.
              Outros gatilhos habilitados registram a consulta na Central.
            </p>
            <GoLink href="/operacoes">Acompanhar workflows</GoLink>
            {state.githubEvents.map((event) => (
              <div key={event.id} className="border-t py-4">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <p className="text-sm font-medium">{event.title}</p>
                  <Badge variant="outline">{EVENT_LABELS[event.type]}</Badge>
                </div>
                <p className="mt-2 text-xs text-muted-foreground">
                  {getRepoName(state, event.repoId)} ·{" "}
                  {getProjectIdentifier(state, event.projectId)} ·{" "}
                  {formatDate(event.timestamp)}
                </p>
                <p className="mt-1 text-sm text-muted-foreground">
                  {event.description}
                </p>
              </div>
            ))}
            {!state.githubEvents.length && (
              <Empty text="Simule um evento para iniciar o feed técnico." />
            )}
          </CardContent>
        </Card>
      )}
    </div>
  );
}
export default function IntegrationsPage() {
  const { state, transact } = useApp();
  const [selected, setSelected] = useState("int-drive");
  const current = state.integrations.find((i) => i.id === selected)!;
  return (
    <PageContainer>
      <Intro
        title="Conecte o contexto do projeto"
        description="Documentos, atividades e desenvolvimento técnico em um mesmo fluxo operacional."
      />
      <Notice>
        Integrações simuladas. As conexões abaixo usam dados fictícios e não
        pedem credenciais.
      </Notice>
      <div className="grid gap-4 md:grid-cols-3">
        {state.integrations.map((integration) => {
          const Icon = ICONS[integration.provider],
            connected = integration.status === "connected";
          return (
            <Card
              key={integration.id}
              className={
                selected === integration.id
                  ? "border-emerald-700 ring-1 ring-emerald-700/10"
                  : ""
              }
            >
              <CardContent className="space-y-4 pt-6">
                <div className="flex items-center justify-between">
                  <div className="rounded-xl bg-muted p-3">
                    <Icon className="h-6 w-6" />
                  </div>
                  <Badge variant={connected ? "success" : "secondary"}>
                    {connected ? "Conectado · simulado" : "Desconectado"}
                  </Badge>
                </div>
                <h3 className="text-lg font-semibold">{integration.label}</h3>
                <p className="min-h-10 text-sm text-muted-foreground">
                  {integration.description}
                </p>
                <div className="flex flex-wrap gap-2">
                  <Button
                    size="sm"
                    variant={connected ? "outline" : "default"}
                    onClick={() =>
                      transact(
                        (s) =>
                          saveIntegration(s, integration.id, {
                            status: connected ? "disconnected" : "connected",
                            config: Object.keys(integration.config).length
                              ? integration.config
                              : defaultConfig(integration.provider),
                          }),
                        connected
                          ? "Integração simulada desconectada"
                          : "Conexão fictícia configurada",
                      )
                    }
                  >
                    <Plug className="mr-2 h-3.5 w-3.5" />
                    {connected
                      ? "Desconectar"
                      : integration.provider === "github"
                        ? "Instalar App simulada"
                        : "Simular conexão"}
                  </Button>
                  <Button
                    aria-label={`Configurar ${integration.label}`}
                    variant="ghost"
                    size="sm"
                    onClick={() => setSelected(integration.id)}
                  >
                    <Settings2 className="mr-2 h-3.5 w-3.5" />
                    Configurar
                  </Button>
                </div>
                {connected && (
                  <p className="flex items-center gap-1 text-xs text-emerald-700">
                    <CheckCircle2 className="h-3 w-3" />
                    Dados restritos à demonstração
                  </p>
                )}
              </CardContent>
            </Card>
          );
        })}
      </div>
      <IntegrationSettings
        key={`${current.id}-${current.status}`}
        integration={current}
      />
    </PageContainer>
  );
}
