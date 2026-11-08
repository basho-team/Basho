import type {
  Activity,
  AgentRun,
  AgentStep,
  AppState,
  ApprovalStatus,
  GithubEvent,
  GithubEventType,
  ScenarioId,
  SimulationCommand,
} from "../types";
import { appendAudit, makeDocument, timestamp, uid } from "./simulationService";
import { simulatedAdapter } from "./adapters";

export const SCENARIOS = [
  {
    id: "A" as const,
    title: "Atualização técnica",
    description: "PR integrado → evidência → atividade → relatório no Drive.",
    triggerLabel: "Simular PR integrado",
  },
  {
    id: "B" as const,
    title: "Organização documental",
    description:
      "Documento recebido → classificação → cópia ou movimentação segura.",
    triggerLabel: "Simular documento",
  },
  {
    id: "C" as const,
    title: "Intervenção humana",
    description: "Evidência insuficiente → decisão humana → retomada auditada.",
    triggerLabel: "Simular exceção",
  },
];
function createRun(
  state: AppState,
  scenario: ScenarioId,
  projectId: string,
  trigger: string,
  commands: Array<[string, SimulationCommand]>,
  sourceEventId?: string,
): AppState {
  if (
    sourceEventId &&
    state.agentRuns.some((r) => r.sourceEventId === sourceEventId)
  )
    return state;
  const id = uid("run"),
    now = timestamp();
  const steps: AgentStep[] = commands.map(([label, command], index) => ({
    id: uid("step"),
    sequence: index + 1,
    label,
    description: label,
    tool: command.kind,
    status: "waiting",
    timestamp: now,
    command,
  }));
  const run: AgentRun = {
    id,
    scenario,
    sourceEventId,
    triggerEvent: trigger,
    triggerSource:
      scenario === "A"
        ? "github"
        : scenario === "B"
          ? "google_drive"
          : "notion",
    module:
      scenario === "A"
        ? "technical"
        : scenario === "B"
          ? "documental"
          : "compliance",
    status: "running",
    steps,
    cursor: 0,
    startedAt: now,
    completedAt: null,
    projectId,
    correlationId: id,
    isSynthetic: true,
  };
  return appendAudit(
    { ...state, agentRuns: [run, ...state.agentRuns] },
    {
      executionId: id,
      eventOrigin: run.triggerSource,
      operation: "workflow.started",
      resourceAffected: projectId,
      result: "running",
      justification: trigger,
      actor: "Orquestrador determinístico",
    },
  );
}
export function generateGithubEvent(
  type: GithubEventType,
  repoId: string,
  state: AppState,
): GithubEvent {
  const repo = state.githubRepos.find((r) => r.id === repoId);
  const titles: Record<GithubEventType, string> = {
    commit: "Commit: validação dos experimentos",
    pr_merged: "Pull request integrado: evolução do protótipo",
    pr_opened: "Pull request aberto para revisão",
    issue_opened: "Issue criada: documentar hipótese técnica",
    issue_closed: "Issue encerrada",
    ci_passed: "Pipeline de testes concluído",
    ci_failed: "Falha no pipeline de testes",
    release: "Release do protótipo publicada",
  };
  return {
    id: uid("event"),
    repoId,
    type,
    title: titles[type],
    description: `Evento sintético em ${repo?.fullName ?? repoId}.`,
    author: "equipe-demo",
    sha: "demo0001",
    url: "",
    timestamp: timestamp(),
    projectId: repo?.projectId,
    isSynthetic: true,
  };
}
function technicalWorkflow(state: AppState, event: GithubEvent): AppState {
  const project = state.projects.find(
    (p) =>
      p.id === state.githubRepos.find((r) => r.id === event.repoId)?.projectId,
  );
  if (!project)
    return appendAudit(state, {
      eventOrigin: "github",
      operation: "workflow.unmapped",
      resourceAffected: event.repoId,
      result: "blocked",
      justification: "Associe o repositório a um projeto",
      actor: "Orquestrador",
    });
  const activity = state.activities.find(
    (a) => a.projectId === project.id && a.status !== "done",
  );
  const evidenceId = uid("evidence");
  const folder = state.integrations.find((i) => i.provider === "google_drive")
    ?.config.agentWorkFolderId;
  const workFolder =
    state.driveItems.find(
      (d) => d.id === folder && (!d.projectId || d.projectId === project.id),
    )?.id ??
    state.driveItems.find(
      (d) =>
        d.type === "folder" &&
        d.projectId === project.id &&
        d.name === "Relatórios Técnicos",
    )?.id ??
    "";
  const report = makeDocument(
    `Evolução técnica — ${event.id.slice(-8)}.md`,
    workFolder,
    project.id,
    `# Registro preliminar de evolução técnica\n\nAmbiente de demonstração — dados sintéticos.\n\nProjeto: ${project.identifier}\nEvento: ${event.id}\nRepositório: ${event.repoId}\nDescrição: ${event.description}\nEvidência: ${evidenceId}\n\nRegistro técnico para revisão. Não comprova elegibilidade, horas, despesas ou enquadramento fiscal.`,
    "report",
  );
  report.createdBy = "agent";
  const commands: Array<[string, SimulationCommand]> = [
    [
      "Evento recebido e repositório identificado",
      {
        kind: "inspect",
        provider: "github",
        operation: "read_events",
        resourceId: event.repoId,
        projectId: project.id,
      },
    ],
    [
      "Projeto relacionado localizado",
      {
        kind: "inspect",
        provider: "github",
        operation: "monitor_repos",
        resourceId: event.repoId,
        projectId: project.id,
      },
    ],
    [
      "Registrar evidência técnica",
      {
        kind: "evidence.create",
        evidence: {
          id: evidenceId,
          projectId: project.id,
          claim: event.title,
          source: "github",
          sourceRef: event.id,
          status: "pending",
          confidence: 1,
          reason:
            "Evento sintético; requer análise técnica, sem inferência fiscal",
          generatedBy: "Módulo técnico simulado",
          relatedActivityId: activity?.id,
          createdAt: timestamp(),
          isSynthetic: true,
        },
      },
    ],
    [
      "Consultar base de atividades",
      {
        kind: "inspect",
        provider: "notion",
        operation: "read_activities",
        resourceId: activity?.id ?? project.id,
        projectId: project.id,
      },
    ],
  ];
  if (activity) {
    commands.push([
      "Atualizar atividade vinculada",
      {
        kind: "activity.annotate",
        id: activity.id,
        entry: `Atualização técnica recebida: ${event.id}. Aguardando revisão.`,
      },
    ]);
    commands.push([
      "Vincular evidência à atividade",
      { kind: "activity.attach_evidence", id: activity.id, evidenceId },
    ]);
  } else {
    const created: Activity = {
      id: uid("activity"),
      title: event.title,
      description: event.description,
      projectId: project.id,
      assignee: project.responsible,
      priority: "medium",
      status: "review",
      dueDate: null,
      evidenceIds: [evidenceId],
      origin: "github",
      history: [],
      createdAt: timestamp(),
      modifiedAt: timestamp(),
      isSynthetic: true,
    };
    commands.push([
      "Criar atividade vinculada à evidência",
      { kind: "activity.create", activity: created },
    ]);
  }
  commands.push([
    "Gerar e armazenar relatório técnico no Drive",
    { kind: "drive.create", item: report },
  ]);
  commands.push([
    "Conferir documento e registrar auditoria",
    {
      kind: "inspect",
      provider: "google_drive",
      operation: "read_files",
      resourceId: report.id,
      projectId: project.id,
    },
  ]);
  return createRun(state, "A", project.id, event.title, commands, event.id);
}
export function receiveGithubEvent(
  state: AppState,
  type: GithubEventType,
  repoId: string,
): AppState {
  const event = generateGithubEvent(type, repoId, state);
  let next = appendAudit(
    { ...state, githubEvents: [event, ...state.githubEvents] },
    {
      eventOrigin: "github",
      operation: "event.received",
      resourceAffected: event.id,
      result: "received",
      actor: "Conector GitHub simulado",
    },
  );
  const integration = state.integrations.find((i) => i.provider === "github");
  if (
    integration?.status !== "connected" ||
    !integration.config.monitoredRepoIds?.includes(repoId) ||
    !integration.config.eventTriggers?.includes(type)
  )
    return next;
  if (type === "pr_merged") return technicalWorkflow(next, event);
  if (type === "ci_failed" && event.projectId)
    return exceptionWorkflow(next, event.projectId, event.id);
  if (event.projectId)
    next = createRun(
      next,
      "A",
      event.projectId,
      event.title,
      [
        [
          "Consultar evento técnico monitorado",
          {
            kind: "inspect",
            provider: "github",
            operation: "read_events",
            resourceId: repoId,
            projectId: event.projectId,
          },
        ],
      ],
      event.id,
    );
  return next;
}
function documentWorkflow(
  state: AppState,
  projectId: string,
  original: boolean,
): AppState {
  const project = state.projects.find((p) => p.id === projectId)!;
  const config = state.integrations.find(
    (i) => i.provider === "google_drive",
  )?.config;
  const source = makeDocument(
    `${original ? "Comprovante original" : "Experimento derivado"} — ${uid("entrada").slice(-8)}.md`,
    project.driveFolderIds[0],
    projectId,
    "Documento inteiramente sintético para a demonstração.",
    original ? "invoice" : "evidence",
  );
  source.isOriginal = original;
  source.isProtected = original;
  source.createdBy = "system";
  const destination = config?.agentWorkFolderId ?? "";
  const copy = {
    ...source,
    id: uid("copy"),
    parentId: destination,
    name: `Cópia de trabalho — ${source.name}`,
    isOriginal: false,
    isProtected: false,
    derivedFromId: source.id,
    createdBy: "agent" as const,
  };
  const next = appendAudit(
    { ...state, driveItems: [...state.driveItems, source] },
    {
      eventOrigin: "google_drive",
      operation: "document.received",
      resourceAffected: source.id,
      newState: JSON.stringify(source),
      result: "received",
      justification: "Entrada externa sintética; original preservado",
      actor: "Conector Drive simulado",
    },
  );
  return createRun(next, "B", projectId, `Documento recebido: ${source.name}`, [
    [
      "Identificar arquivo e metadados do projeto",
      {
        kind: "inspect",
        provider: "google_drive",
        operation: "read_files",
        resourceId: source.id,
        projectId,
      },
    ],
    [
      "Classificar documento e conferir destino",
      {
        kind: "inspect",
        provider: "google_drive",
        operation: "read_files",
        resourceId: destination,
        projectId,
      },
    ],
    [
      original
        ? "Preservar original e criar cópia de trabalho"
        : "Mover documento derivado para pasta autorizada",
      original
        ? { kind: "drive.copy", sourceId: source.id, item: copy }
        : {
            kind: "drive.update",
            id: source.id,
            patch: { parentId: destination },
          },
    ],
    [
      "Conferir registro documental e histórico",
      {
        kind: "inspect",
        provider: "google_drive",
        operation: "read_files",
        resourceId: original ? copy.id : source.id,
        projectId,
      },
    ],
  ]);
}
function exceptionWorkflow(
  state: AppState,
  projectId: string,
  sourceEventId?: string,
): AppState {
  const activity = state.activities.find(
    (a) =>
      a.projectId === projectId && !a.evidenceIds.length && a.status !== "done",
  );
  if (!activity)
    return appendAudit(state, {
      eventOrigin: "notion",
      operation: "consistency.scan",
      resourceAffected: projectId,
      result: "completed",
      justification: "Nenhuma atividade aberta sem evidências neste projeto",
      actor: "Módulo de conformidade simulado",
    });
  return createRun(
    state,
    "C",
    projectId,
    `Evidências insuficientes: ${activity.title}`,
    [
      [
        "Consultar atividade e detectar falta de evidências",
        {
          kind: "inspect",
          provider: "notion",
          operation: "read_activities",
          resourceId: activity.id,
          projectId,
        },
      ],
      [
        "Solicitar decisão sobre encaminhamento para revisão",
        { kind: "review", activityId: activity.id, projectId },
      ],
      [
        "Conferir atividade após decisão humana",
        {
          kind: "inspect",
          provider: "notion",
          operation: "read_activities",
          resourceId: activity.id,
          projectId,
        },
      ],
    ],
    sourceEventId,
  );
}
export function startScenario(
  state: AppState,
  scenario: ScenarioId,
  projectId = state.projects[0].id,
  original = true,
): AppState {
  if (scenario === "B") return documentWorkflow(state, projectId, original);
  if (scenario === "C") return exceptionWorkflow(state, projectId);
  const repo = state.githubRepos.find((r) => r.projectId === projectId);
  if (!repo)
    return appendAudit(state, {
      eventOrigin: "github",
      operation: "workflow.unmapped",
      resourceAffected: projectId,
      result: "blocked",
      justification: "Vincule um repositório ao projeto",
      actor: "Simulador",
    });
  const event = generateGithubEvent("pr_merged", repo.id, state);
  return technicalWorkflow(
    { ...state, githubEvents: [event, ...state.githubEvents] },
    event,
  );
}
function patchRun(
  state: AppState,
  id: string,
  patch: Partial<AgentRun>,
): AppState {
  return {
    ...state,
    agentRuns: state.agentRuns.map((r) =>
      r.id === id ? { ...r, ...patch } : r,
    ),
  };
}
export function advanceRun(state: AppState, runId: string): AppState {
  const run = state.agentRuns.find((r) => r.id === runId);
  if (!run || run.status !== "running") return state;
  const cursor = run.cursor ?? 0,
    step = run.steps[cursor];
  if (!step?.command)
    return patchRun(state, runId, {
      status: "failed",
      error: "Plano de execução ausente",
      completedAt: timestamp(),
    });
  const approval = state.approvalRequests.find(
    (a) => a.runId === runId && a.stepId === step.id && a.status === "approved",
  );
  const result = simulatedAdapter.execute(state, step.command, {
    runId,
    stepId: step.id,
    actor: `Módulo ${run.module} simulado`,
    approvalId: approval?.id,
  });
  const status =
    result.outcome === "blocked"
      ? "blocked_by_policy"
      : result.outcome === "pending_approval"
        ? "awaiting_approval"
        : "completed";
  const log = result.state.auditLogs[0];
  const steps: AgentStep[] = run.steps.map((s, i) =>
    i === cursor
      ? {
          ...s,
          status,
          result: result.message,
          timestamp: timestamp(),
          policyApplied: log.policyApplied,
          resourceAffected: log.resourceAffected,
        }
      : s,
  );
  const complete = result.outcome === "executed" && cursor + 1 === steps.length;
  let next = patchRun(result.state, runId, {
    steps,
    cursor: result.outcome === "executed" ? cursor + 1 : cursor,
    status: complete
      ? "completed"
      : result.outcome === "executed"
        ? "running"
        : status,
    completedAt:
      complete || status === "blocked_by_policy" ? timestamp() : null,
    result: complete
      ? "Etapas concluídas; alterações e evidências disponíveis nos módulos vinculados."
      : result.message,
  });
  if (complete)
    next = appendAudit(next, {
      executionId: runId,
      eventOrigin: run.triggerSource,
      operation: "workflow.completed",
      resourceAffected: run.projectId ?? runId,
      result: "completed",
      actor: "Orquestrador determinístico",
    });
  return next;
}
export function resolveApproval(
  state: AppState,
  id: string,
  decision: ApprovalStatus,
  note: string,
): AppState {
  const approval = state.approvalRequests.find((a) => a.id === id);
  if (!approval || !["pending", "needs_revision"].includes(approval.status))
    return state;
  if (decision !== "approved" && !note.trim()) return state;
  let next = {
    ...state,
    approvalRequests: state.approvalRequests.map((a) =>
      a.id === id
        ? {
            ...a,
            status: decision,
            resolutionNote: note,
            resolvedAt: decision === "pending" ? null : timestamp(),
            resolvedBy: "Responsável da demonstração",
          }
        : a,
    ),
  };
  next = appendAudit(next, {
    executionId: approval.runId,
    eventOrigin: "human",
    operation: `approval.${decision}`,
    resourceAffected: id,
    previousState: approval.status,
    newState: decision,
    result: decision,
    justification: note || "Autorização individual registrada",
    actor: "Responsável da demonstração",
  });
  if (approval.runId) {
    if (decision === "approved")
      return patchRun(next, approval.runId, {
        status: "running",
        result: "Decisão registrada. Retomando a etapa preparada.",
      });
    if (decision === "rejected")
      return patchRun(next, approval.runId, {
        status: "failed",
        error: note,
        result: "Execução encerrada por rejeição humana",
        completedAt: timestamp(),
      });
    return patchRun(next, approval.runId, {
      status: "awaiting_approval",
      result:
        decision === "pending"
          ? "Reenviado para decisão"
          : `Complementação solicitada: ${note}`,
    });
  }
  if (decision === "approved" && approval.command)
    return simulatedAdapter.execute(next, approval.command, { approvalId: id })
      .state;
  return next;
}
export function retryRun(state: AppState, id: string): AppState {
  const run = state.agentRuns.find((r) => r.id === id);
  if (!run || run.status !== "blocked_by_policy") return state;
  return appendAudit(
    patchRun(state, id, {
      status: "running",
      completedAt: null,
      error: undefined,
    }),
    {
      executionId: id,
      eventOrigin: "human",
      operation: "workflow.retry",
      resourceAffected: id,
      result: "running",
      justification: "Revalidar políticas atuais na etapa bloqueada",
      actor: "Operador",
    },
  );
}
