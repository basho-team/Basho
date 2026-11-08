import type {
  AppState,
  AuditLog,
  DriveItem,
  SimulationCommand,
  SimulationResult,
} from "../types";
import { authorize, commandScope } from "./permissionService";

export const uid = (prefix = "id") =>
  `${prefix}-${globalThis.crypto.randomUUID()}`;
export const timestamp = () => new Date().toISOString();
export function appendAudit(
  state: AppState,
  entry: Omit<AuditLog, "id" | "timestamp">,
): AppState {
  return {
    ...state,
    auditLogs: [
      { ...entry, id: uid("log"), timestamp: timestamp() },
      ...state.auditLogs,
    ],
  };
}
export function reconcile(state: AppState): AppState {
  return {
    ...state,
    projects: state.projects.map((p) => ({
      ...p,
      activityIds: state.activities
        .filter((a) => a.projectId === p.id)
        .map((a) => a.id),
      repoIds: state.githubRepos
        .filter((r) => r.projectId === p.id)
        .map((r) => r.id),
      evidenceIds: state.evidence
        .filter((e) => e.projectId === p.id)
        .map((e) => e.id),
      reportIds: state.driveItems
        .filter((d) => d.projectId === p.id && d.category === "report")
        .map((d) => d.id),
      financialDocIds: state.driveItems
        .filter(
          (d) =>
            d.projectId === p.id &&
            ["invoice", "contract", "spreadsheet", "financial_doc"].includes(
              d.category ?? "",
            ),
        )
        .map((d) => d.id),
      completeness: completeness(state, p.id),
    })),
  };
}
export function completeness(state: AppState, projectId: string): number {
  const items = state.leiDoBemItems.filter((i) => i.projectId === projectId);
  const present = items.filter(
    (i) =>
      ["present", "validated"].includes(i.status) &&
      ((!!i.documentId &&
        state.driveItems.some(
          (d) => d.id === i.documentId && d.projectId === projectId,
        )) ||
        (i.type === "objectives" &&
          !!state.projects.find((p) => p.id === projectId)?.objectives.trim())),
  );
  return items.length ? Math.round((present.length / items.length) * 100) : 0;
}
export function makeDocument(
  name: string,
  parentId: string,
  projectId: string,
  content = "",
  category: DriveItem["category"] = "technical_doc",
): DriveItem {
  const now = timestamp();
  return {
    id: uid("doc"),
    name,
    parentId,
    projectId,
    content,
    category,
    type: "file",
    mimeType: "text/markdown",
    isOriginal: false,
    isProtected: false,
    createdAt: now,
    modifiedAt: now,
    createdBy: "user",
    isSynthetic: true,
  };
}
function descendants(state: AppState, id: string): string[] {
  const ids = new Set([id]);
  let size = 0;
  while (size !== ids.size) {
    size = ids.size;
    state.driveItems.forEach((d) => {
      if (d.parentId && ids.has(d.parentId)) ids.add(d.id);
    });
  }
  return [...ids];
}
function validateDrive(
  state: AppState,
  cmd: Extract<
    SimulationCommand,
    { kind: "drive.create" | "drive.copy" | "drive.update" }
  >,
): string | undefined {
  const item =
    cmd.kind === "drive.update"
      ? state.driveItems.find((d) => d.id === cmd.id)
      : cmd.item;
  if (!item) return "Recurso não encontrado";
  const parentId =
    cmd.kind === "drive.update"
      ? (cmd.patch.parentId ?? item.parentId)
      : item.parentId;
  const parent = state.driveItems.find(
    (d) => d.id === parentId && d.type === "folder",
  );
  if (!parent) return "Selecione uma pasta de destino válida";
  const name =
    cmd.kind === "drive.update" ? (cmd.patch.name ?? item.name) : item.name;
  if (!name.trim() || name.length > 180)
    return "Informe um nome entre 1 e 180 caracteres";
  if (
    state.driveItems.some(
      (d) => d.id !== item.id && d.parentId === parentId && d.name === name,
    )
  )
    return "Já existe um recurso com esse nome na pasta";
  if (
    cmd.kind !== "drive.update" &&
    state.driveItems.some((d) => d.id === item.id)
  )
    return "Identificador já existe";
  if (item.projectId && parent.projectId && item.projectId !== parent.projectId)
    return "Mantenha o documento nas pastas de seu projeto";
  if (cmd.kind === "drive.update") {
    const ids = descendants(state, item.id);
    if (
      state.driveItems.some(
        (d) =>
          ids.includes(d.id) &&
          (d.isProtected || (d.type === "file" && d.isOriginal)),
      )
    )
      return "Original protegido: crie uma cópia de trabalho";
    if (cmd.patch.parentId && ids.includes(cmd.patch.parentId))
      return "Uma pasta não pode ser movida para dentro dela mesma";
  }
  if (
    cmd.kind === "drive.copy" &&
    !state.driveItems.some((d) => d.id === cmd.sourceId && d.type === "file")
  )
    return "Selecione um arquivo para copiar";
}
function validateCommand(
  state: AppState,
  cmd: SimulationCommand,
): string | undefined {
  if (
    cmd.kind === "drive.create" ||
    cmd.kind === "drive.copy" ||
    cmd.kind === "drive.update"
  )
    return validateDrive(state, cmd);
  if (cmd.kind === "activity.create") {
    if (
      !cmd.activity.title.trim() ||
      !cmd.activity.assignee.trim() ||
      !state.projects.some((p) => p.id === cmd.activity.projectId)
    )
      return "Informe título, responsável e projeto válidos";
    if (state.activities.some((a) => a.id === cmd.activity.id))
      return "Atividade já existe";
    if (
      cmd.activity.evidenceIds.some(
        (id) =>
          !state.evidence.some(
            (e) => e.id === id && e.projectId === cmd.activity.projectId,
          ),
      )
    )
      return "Evidência incompatível com o projeto";
  }
  if (cmd.kind === "activity.attach_evidence") {
    const activity = state.activities.find((a) => a.id === cmd.id);
    if (
      !activity ||
      !state.evidence.some(
        (e) => e.id === cmd.evidenceId && e.projectId === activity.projectId,
      )
    )
      return "Evidência ou atividade incompatível";
  }
  if (
    cmd.kind === "activity.annotate" &&
    !state.activities.some((a) => a.id === cmd.id)
  )
    return "Atividade não encontrada";
  if (cmd.kind === "activity.update" || cmd.kind === "review") {
    const activity = state.activities.find(
      (a) => a.id === (cmd.kind === "review" ? cmd.activityId : cmd.id),
    );
    if (!activity) return "Atividade não encontrada";
    if (cmd.kind === "activity.update") {
      if (cmd.patch.title !== undefined && !cmd.patch.title.trim())
        return "O título é obrigatório";
      if (cmd.patch.assignee !== undefined && !cmd.patch.assignee.trim())
        return "O responsável é obrigatório";
      if (
        cmd.patch.evidenceIds?.some(
          (id) =>
            !state.evidence.some(
              (e) => e.id === id && e.projectId === activity.projectId,
            ),
        )
      )
        return "Evidência incompatível com o projeto";
    }
  }
  if (
    cmd.kind === "evidence.create" &&
    state.evidence.some((e) => e.id === cmd.evidence.id)
  )
    return "Evidência já registrada";
  if (cmd.kind === "checklist.update") {
    const item = state.leiDoBemItems.find((i) => i.id === cmd.id);
    if (!item) return "Item documental não encontrado";
    if (
      ["present", "validated"].includes(cmd.status) &&
      !state.driveItems.some(
        (d) => d.id === cmd.documentId && d.projectId === item.projectId,
      ) &&
      item.type !== "objectives"
    )
      return "Vincule um documento do projeto para registrar presença ou validação";
    if (cmd.status === "validated" && !cmd.validatedBy?.trim())
      return "Informe o responsável pela validação";
  }
}
function applyMutation(
  state: AppState,
  command: SimulationCommand,
  actor: string,
): AppState {
  const now = timestamp();
  switch (command.kind) {
    case "inspect":
      return state;
    case "drive.create":
      return { ...state, driveItems: [...state.driveItems, command.item] };
    case "drive.copy": {
      const source = state.driveItems.find((d) => d.id === command.sourceId)!;
      return {
        ...state,
        driveItems: [
          ...state.driveItems,
          {
            ...source,
            ...command.item,
            content: source.content,
            derivedFromId: source.id,
            isOriginal: false,
            isProtected: false,
          },
        ],
      };
    }
    case "drive.update":
      return {
        ...state,
        driveItems: state.driveItems.map((d) =>
          d.id === command.id ? { ...d, ...command.patch, modifiedAt: now } : d,
        ),
      };
    case "activity.create":
      return { ...state, activities: [...state.activities, command.activity] };
    case "activity.attach_evidence": {
      const activity = state.activities.find((a) => a.id === command.id)!;
      return applyMutation(
        state,
        {
          kind: "activity.update",
          id: activity.id,
          patch: {
            evidenceIds: [
              ...new Set([...activity.evidenceIds, command.evidenceId]),
            ],
          },
        },
        actor,
      );
    }
    case "activity.annotate": {
      const activity = state.activities.find((a) => a.id === command.id)!;
      return applyMutation(
        state,
        {
          kind: "activity.update",
          id: activity.id,
          patch: {
            status: "review",
            description: `${activity.description}\n\n${command.entry}`,
          },
        },
        actor,
      );
    }
    case "activity.update":
      return {
        ...state,
        activities: state.activities.map((a) =>
          a.id === command.id
            ? {
                ...a,
                ...command.patch,
                modifiedAt: now,
                history: [
                  ...a.history,
                  {
                    id: uid("hist"),
                    timestamp: now,
                    actor,
                    action: "Atividade atualizada",
                    oldValue: JSON.stringify(a),
                    newValue: JSON.stringify(command.patch),
                  },
                ],
              }
            : a,
        ),
      };
    case "review":
      return applyMutation(
        state,
        {
          kind: "activity.update",
          id: command.activityId,
          patch: { status: "review" },
        },
        actor,
      );
    case "evidence.create":
      return { ...state, evidence: [command.evidence, ...state.evidence] };
    case "checklist.update":
      return {
        ...state,
        leiDoBemItems: state.leiDoBemItems.map((i) =>
          i.id === command.id
            ? {
                ...i,
                status: command.status,
                documentId: command.documentId,
                validatedBy:
                  command.status === "validated"
                    ? command.validatedBy
                    : undefined,
                lastModified: now,
              }
            : i,
        ),
      };
  }
}
function snapshot(state: AppState, cmd: SimulationCommand): string {
  switch (cmd.kind) {
    case "drive.create":
    case "drive.copy":
      return JSON.stringify(
        state.driveItems.find((d) => d.id === cmd.item.id) ?? null,
      );
    case "drive.update":
      return JSON.stringify(
        state.driveItems.find((d) => d.id === cmd.id) ?? null,
      );
    case "activity.create":
      return JSON.stringify(
        state.activities.find((a) => a.id === cmd.activity.id) ?? null,
      );
    case "activity.attach_evidence":
    case "activity.annotate":
    case "activity.update":
      return JSON.stringify(
        state.activities.find((a) => a.id === cmd.id) ?? null,
      );
    case "review":
      return JSON.stringify(
        state.activities.find((a) => a.id === cmd.activityId) ?? null,
      );
    case "evidence.create":
      return JSON.stringify(
        state.evidence.find((e) => e.id === cmd.evidence.id) ?? null,
      );
    case "checklist.update":
      return JSON.stringify(
        state.leiDoBemItems.find((i) => i.id === cmd.id) ?? null,
      );
    default:
      return "Consulta sem alteração";
  }
}
export function executeCommand(
  state: AppState,
  command: SimulationCommand,
  options: {
    actor?: string;
    runId?: string;
    stepId?: string;
    approvalId?: string;
  } = {},
): SimulationResult {
  const scope = commandScope(state, command);
  const actor = options.actor ?? "Operador da demonstração";
  const validation = validateCommand(state, command);
  const permission = authorize(state, command);
  const grant = state.approvalRequests.find(
    (a) =>
      a.id === options.approvalId &&
      a.status === "approved" &&
      a.runId === options.runId &&
      a.stepId === options.stepId &&
      JSON.stringify(a.command) === JSON.stringify(command),
  );
  const blocked = !!validation || permission.level === "blocked";
  const needsApproval =
    !blocked &&
    !grant &&
    (permission.level === "requires_approval" || command.kind === "review");
  const outcome = blocked
    ? "blocked"
    : needsApproval
      ? "pending_approval"
      : "executed";
  const message =
    validation ??
    (blocked
      ? permission.reason
      : needsApproval
        ? "Ação preparada. Decisão pendente em Aprovações."
        : "Operação concluída");
  let next = state;
  if (needsApproval)
    next = {
      ...next,
      approvalRequests: [
        {
          id: uid("approval"),
          runId: options.runId,
          stepId: options.stepId,
          command,
          class: command.kind === "review" ? "A2" : "A1",
          title:
            command.kind === "review"
              ? "Atividade sem evidências suficientes"
              : `Autorizar ${scope.operations.join(", ")}`,
          description:
            command.kind === "review"
              ? "A atividade não possui evidências. Decida sobre encaminhá-la para revisão técnica; esta decisão não valida elegibilidade fiscal."
              : "Uma política exige autorização individual. A ação permanece suspensa até a decisão.",
          context: [
            { label: "Recurso", value: scope.resourceId },
            { label: "Projeto", value: scope.projectId ?? "Geral" },
            { label: "Ação preparada", value: JSON.stringify(command) },
          ],
          status: "pending",
          requestedAt: timestamp(),
          resolvedAt: null,
          resolvedBy: null,
          projectId: scope.projectId,
          isSynthetic: true,
        },
        ...next.approvalRequests,
      ],
    };
  if (outcome === "executed")
    next = reconcile(applyMutation(next, command, actor));
  next = appendAudit(next, {
    executionId: options.runId,
    eventOrigin: scope.provider,
    operation: command.kind,
    resourceAffected: scope.resourceId,
    previousState: snapshot(state, command),
    newState: snapshot(next, command),
    result: outcome,
    justification: message,
    policyApplied: permission.level,
    actor,
  });
  if (outcome === "executed" && scope.projectId && command.kind !== "inspect")
    next = {
      ...next,
      projects: next.projects.map((p) =>
        p.id === scope.projectId
          ? {
              ...p,
              history: [
                ...p.history,
                {
                  id: uid("ph"),
                  timestamp: timestamp(),
                  actor,
                  action: `${command.kind}: ${scope.resourceId}`,
                },
              ],
            }
          : p,
      ),
    };
  return { state: next, outcome, message };
}
