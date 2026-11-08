import type {
  AppState,
  Integration,
  IntegrationConfig,
  IntegrationProvider,
  PermissionLevel,
  PermissionPolicy,
} from "../types";
import { appendAudit, reconcile, timestamp, uid } from "./simulationService";

export function defaultConfig(
  provider: IntegrationProvider,
): IntegrationConfig {
  if (provider === "google_drive")
    return {
      rootFolderUrl: "https://drive.google.com/drive/folders/demo-root",
      agentWorkFolderId: "drive-folder-pd001-agent-work",
      readableFolderIds: ["drive-folder-root"],
      writableFolderIds: ["drive-folder-root"],
      autoOrganizeFolderIds: ["drive-folder-root"],
    };
  if (provider === "notion")
    return {
      workspaceId: "workspace-basho-demo",
      databaseId: "database-activities",
      databaseName: "Atividades de PD&I",
      allowCreateTasks: true,
      allowEditTasks: true,
    };
  return {
    installationId: "app-demo",
    orgOrUser: "basho-tech",
    monitoredRepoIds: ["gh-repo-1", "gh-repo-2"],
    eventTriggers: ["pr_merged", "ci_failed"],
  };
}
export function saveIntegration(
  state: AppState,
  id: string,
  patch: Partial<Pick<Integration, "status" | "config">>,
): AppState {
  const old = state.integrations.find((i) => i.id === id);
  if (!old) throw new Error("Integração não encontrada");
  const config = patch.config ?? old.config;
  if (old.provider === "google_drive") {
    if (
      config.rootFolderUrl &&
      !/^https:\/\/drive\.google\.com\/.*folders\/[A-Za-z0-9_-]+/.test(
        config.rootFolderUrl,
      )
    )
      throw new Error(
        "Informe um link de pasta válido do Google Drive (somente configuração simulada)",
      );
    const folderIds = state.driveItems
      .filter((d) => d.type === "folder")
      .map((d) => d.id);
    if (
      [
        ...(config.readableFolderIds ?? []),
        ...(config.writableFolderIds ?? []),
        ...(config.autoOrganizeFolderIds ?? []),
        ...(config.agentWorkFolderId ? [config.agentWorkFolderId] : []),
      ].some((id) => !folderIds.includes(id))
    )
      throw new Error("Pasta de configuração inválida");
  }
  const next = {
    ...old,
    ...patch,
    connectedAt:
      patch.status === "connected"
        ? timestamp()
        : patch.status === "disconnected"
          ? null
          : old.connectedAt,
  };
  return appendAudit(
    {
      ...state,
      integrations: state.integrations.map((i) => (i.id === id ? next : i)),
    },
    {
      eventOrigin: "human",
      operation: "integration.configure",
      resourceAffected: id,
      previousState: JSON.stringify(old),
      newState: JSON.stringify(next),
      result: "executed",
      actor: "Operador da demonstração",
    },
  );
}
export function setPolicy(
  state: AppState,
  policy: PermissionPolicy,
  level: PermissionLevel,
  projectId?: string,
  resourceId?: string,
): AppState {
  if (policy.category === "formal" && level !== "blocked")
    throw new Error(
      "Operações formais permanecem bloqueadas nesta demonstração",
    );
  const existing = state.permissionPolicies.find(
    (p) =>
      p.provider === policy.provider &&
      p.operation === policy.operation &&
      p.projectId === projectId &&
      p.resourceId === resourceId,
  );
  const updated = {
    ...policy,
    id: existing?.id ?? uid("policy"),
    projectId,
    resourceId,
    level,
  };
  const policies = existing
    ? state.permissionPolicies.map((p) => (p.id === existing.id ? updated : p))
    : [...state.permissionPolicies, updated];
  return appendAudit(
    { ...state, permissionPolicies: policies },
    {
      eventOrigin: "human",
      operation: "policy.configure",
      resourceAffected: updated.id,
      previousState: JSON.stringify(existing ?? null),
      newState: JSON.stringify(updated),
      result: "executed",
      justification: `Escopo: ${projectId ?? "todos os projetos"} / ${resourceId ?? "todos os recursos"}`,
      actor: "Operador",
    },
  );
}
export function linkRepo(
  state: AppState,
  repoId: string,
  projectId: string,
): AppState {
  const repo = state.githubRepos.find((r) => r.id === repoId);
  if (!repo || !state.projects.some((p) => p.id === projectId))
    throw new Error("Repositório ou projeto inválido");
  return reconcile(
    appendAudit(
      {
        ...state,
        githubRepos: state.githubRepos.map((r) =>
          r.id === repoId ? { ...r, projectId } : r,
        ),
      },
      {
        eventOrigin: "human",
        operation: "repository.link",
        resourceAffected: repoId,
        previousState: repo.projectId,
        newState: projectId,
        result: "executed",
        actor: "Operador",
      },
    ),
  );
}

export function saveProject(
  state: AppState,
  id: string,
  patch: Partial<
    Pick<
      AppState["projects"][0],
      | "name"
      | "description"
      | "objectives"
      | "responsible"
      | "status"
      | "startDate"
      | "endDate"
    >
  >,
): AppState {
  const old = state.projects.find((p) => p.id === id);
  if (!old) throw new Error("Projeto não encontrado");
  const next = { ...old, ...patch };
  if (!next.name.trim() || !next.objectives.trim() || !next.responsible.trim())
    throw new Error("Informe nome, objetivos e responsável");
  if (!next.startDate || !next.endDate || next.endDate < next.startDate)
    throw new Error("Informe um período de execução válido");
  next.history = [
    ...old.history,
    {
      id: uid("ph"),
      timestamp: timestamp(),
      actor: "Operador",
      action: "Dados do projeto atualizados",
    },
  ];
  return reconcile(
    appendAudit(
      {
        ...state,
        projects: state.projects.map((p) => (p.id === id ? next : p)),
      },
      {
        eventOrigin: "human",
        operation: "project.update",
        resourceAffected: id,
        previousState: JSON.stringify(old),
        newState: JSON.stringify(next),
        result: "executed",
        actor: "Operador",
      },
    ),
  );
}
