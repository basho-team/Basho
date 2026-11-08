import type {
  AppState,
  IntegrationProvider,
  PermissionLevel,
  PermissionPolicy,
  SimulationCommand,
} from "../types";

export const POLICY_LABELS: Record<PermissionLevel, string> = {
  automatic: "Automático",
  requires_approval: "Exige aprovação",
  blocked: "Bloqueado",
};
export const PROVIDER_LABELS: Record<IntegrationProvider, string> = {
  google_drive: "Google Drive",
  notion: "Notion",
  github: "GitHub",
};
export interface PermissionCheckResult {
  allowed: boolean;
  level: PermissionLevel;
  policy?: PermissionPolicy;
  reason: string;
}
export function checkPermission(
  policies: PermissionPolicy[],
  provider: IntegrationProvider,
  operation: string,
  projectId?: string,
  resourceId?: string,
): PermissionCheckResult {
  const candidates = policies.filter(
    (p) =>
      p.provider === provider &&
      p.operation === operation &&
      (!p.projectId || p.projectId === projectId) &&
      (!p.resourceId || p.resourceId === resourceId),
  );
  const policy = candidates.sort(
    (a, b) =>
      Number(!!b.resourceId) * 2 +
      Number(!!b.projectId) -
      (Number(!!a.resourceId) * 2 + Number(!!a.projectId)),
  )[0];
  const level =
    policy?.category === "formal" ? "blocked" : (policy?.level ?? "blocked");
  return {
    allowed: level === "automatic",
    level,
    policy,
    reason: policy
      ? POLICY_LABELS[level]
      : "Nenhuma política autoriza esta operação",
  };
}
export function inFolders(
  state: AppState,
  resourceId: string | null,
  folders: string[] = [],
): boolean {
  const visited = new Set<string>();
  let id = resourceId;
  while (id && !visited.has(id)) {
    if (folders.includes(id)) return true;
    visited.add(id);
    id = state.driveItems.find((d) => d.id === id)?.parentId ?? null;
  }
  return false;
}
export interface CommandScope {
  provider: IntegrationProvider;
  operations: string[];
  resourceId: string;
  projectId?: string;
}
export function commandScope(
  state: AppState,
  command: SimulationCommand,
): CommandScope {
  switch (command.kind) {
    case "inspect":
      return { ...command, operations: [command.operation] };
    case "drive.create":
      return {
        provider: "google_drive",
        operations: [
          command.item.type === "folder"
            ? "create_folders"
            : "create_documents",
        ],
        resourceId: command.item.parentId ?? command.item.id,
        projectId: command.item.projectId,
      };
    case "drive.copy":
      return {
        provider: "google_drive",
        operations: ["read_files", "copy_documents"],
        resourceId: command.sourceId,
        projectId: command.item.projectId,
      };
    case "drive.update":
      return {
        provider: "google_drive",
        operations: [
          command.patch.parentId ? "move_derived" : "rename_derived",
        ],
        resourceId: command.id,
        projectId: state.driveItems.find((d) => d.id === command.id)?.projectId,
      };
    case "activity.create":
      return {
        provider: "notion",
        operations: [
          "create_tasks",
          ...(command.activity.status === "done"
            ? ["complete_activities"]
            : []),
          ...(command.activity.evidenceIds.length ? ["add_evidence"] : []),
        ],
        resourceId: command.activity.id,
        projectId: command.activity.projectId,
      };
    case "activity.attach_evidence":
      return {
        provider: "notion",
        operations: ["add_evidence"],
        resourceId: command.id,
        projectId: state.activities.find((a) => a.id === command.id)?.projectId,
      };
    case "activity.annotate":
      return {
        provider: "notion",
        operations: ["update_descriptions", "change_status"],
        resourceId: command.id,
        projectId: state.activities.find((a) => a.id === command.id)?.projectId,
      };
    case "activity.update": {
      const operations = Object.keys(command.patch).map(
        (key) =>
          ({
            title: "update_descriptions",
            description: "update_descriptions",
            dueDate: "update_descriptions",
            status:
              command.patch.status === "done"
                ? "complete_activities"
                : "change_status",
            assignee: "change_assignees",
            priority: "update_priorities",
            evidenceIds: "add_evidence",
          })[key],
      );
      return {
        provider: "notion",
        operations: operations.filter((op): op is string => !!op),
        resourceId: command.id,
        projectId: state.activities.find((a) => a.id === command.id)?.projectId,
      };
    }
    case "evidence.create":
      return {
        provider: "github",
        operations: ["create_evidence_records", "link_commits"],
        resourceId:
          state.githubEvents.find((e) => e.id === command.evidence.sourceRef)
            ?.repoId ?? command.evidence.sourceRef,
        projectId: command.evidence.projectId,
      };
    case "review":
      return {
        provider: "notion",
        operations: ["change_status"],
        resourceId: command.activityId,
        projectId: command.projectId,
      };
    case "checklist.update":
      return {
        provider: "google_drive",
        operations: ["read_files"],
        resourceId:
          command.documentId ??
          state.leiDoBemItems.find((i) => i.id === command.id)?.documentId ??
          "drive-folder-root",
        projectId: state.leiDoBemItems.find((i) => i.id === command.id)
          ?.projectId,
      };
  }
}
export function authorize(
  state: AppState,
  command: SimulationCommand,
): PermissionCheckResult {
  const scope = commandScope(state, command);
  const integration = state.integrations.find(
    (i) => i.provider === scope.provider,
  );
  const deny = (reason: string): PermissionCheckResult => ({
    allowed: false,
    level: "blocked",
    reason,
  });
  if (integration?.status !== "connected")
    return deny(
      `${PROVIDER_LABELS[scope.provider]}: conecte a integração simulada`,
    );
  if (scope.provider === "google_drive") {
    const config = integration.config;
    const readId =
      command.kind === "drive.create"
        ? command.item.parentId
        : scope.resourceId;
    if (!inFolders(state, readId ?? null, config.readableFolderIds))
      return deny("Recurso fora das pastas autorizadas para leitura");
    if (command.kind.startsWith("drive.") && command.kind !== "inspect") {
      const target =
        command.kind === "drive.create" || command.kind === "drive.copy"
          ? command.item.parentId
          : command.kind === "drive.update"
            ? (command.patch.parentId ??
              state.driveItems.find((d) => d.id === command.id)?.parentId)
            : null;
      if (!inFolders(state, target ?? null, config.writableFolderIds))
        return deny("Pasta de destino sem permissão de escrita");
      if (
        command.kind === "drive.update" &&
        !inFolders(state, command.id, config.writableFolderIds)
      )
        return deny("Pasta de origem sem permissão de escrita");
      if (
        command.kind === "drive.update" &&
        command.patch.parentId &&
        !inFolders(state, command.id, config.autoOrganizeFolderIds)
      )
        return deny("Diretório não autorizado para reorganização");
    }
  }
  if (scope.provider === "notion") {
    if (!integration.config.databaseId)
      return deny("Selecione a base de atividades do Notion");
    if (
      command.kind === "activity.create" &&
      !integration.config.allowCreateTasks
    )
      return deny("Criação de tarefas desabilitada na integração");
    if (
      (command.kind === "activity.update" ||
        command.kind === "activity.attach_evidence" ||
        command.kind === "activity.annotate" ||
        command.kind === "review") &&
      !integration.config.allowEditTasks
    )
      return deny("Edição de tarefas desabilitada na integração");
  }
  if (
    scope.provider === "github" &&
    !integration.config.monitoredRepoIds?.includes(scope.resourceId)
  )
    return deny("Repositório fora do monitoramento autorizado");
  const checks = scope.operations.map((op) =>
    checkPermission(
      state.permissionPolicies,
      scope.provider,
      op,
      scope.projectId,
      scope.resourceId,
    ),
  );
  const blocked = checks.find((c) => c.level === "blocked");
  if (blocked) return blocked;
  const pending = checks.find((c) => c.level === "requires_approval");
  return (
    pending ?? {
      allowed: true,
      level: "automatic",
      reason: "Operação autorizada automaticamente",
    }
  );
}
export function policyBadgeVariant(level: PermissionLevel) {
  return level === "automatic"
    ? "success"
    : level === "blocked"
      ? "destructive"
      : "warning";
}
