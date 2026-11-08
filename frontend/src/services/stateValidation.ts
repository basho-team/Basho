import type { AppState } from "../types";

type Rule = (value: unknown) => boolean;
const string: Rule = (value) => typeof value === "string";
const number: Rule = (value) =>
  typeof value === "number" && Number.isFinite(value);
const boolean: Rule = (value) => typeof value === "boolean";
const synthetic: Rule = (value) => value === true;
const optional =
  (rule: Rule): Rule =>
  (value) =>
    value === undefined || rule(value);
const nullable =
  (rule: Rule): Rule =>
  (value) =>
    value === null || rule(value);
const list =
  (rule: Rule): Rule =>
  (value) =>
    Array.isArray(value) && value.every(rule);
const choice =
  (...values: string[]): Rule =>
  (value) =>
    typeof value === "string" && values.includes(value);
function object(fields: Record<string, Rule>): Rule {
  return (value) =>
    typeof value === "object" &&
    value !== null &&
    !Array.isArray(value) &&
    Object.entries(fields).every(([key, rule]) =>
      rule((value as Record<string, unknown>)[key]),
    );
}
const provider = choice("google_drive", "notion", "github");
const permission = choice("automatic", "requires_approval", "blocked");
const activityStatus = choice(
  "todo",
  "in_progress",
  "review",
  "done",
  "blocked",
);
const priority = choice("low", "medium", "high", "urgent");
const documentStatus = choice(
  "present",
  "absent",
  "draft",
  "pending_review",
  "validated",
);
const runStatus = choice(
  "waiting",
  "running",
  "completed",
  "failed",
  "awaiting_approval",
  "blocked_by_policy",
);
const eventType = choice(
  "commit",
  "pr_merged",
  "pr_opened",
  "issue_opened",
  "issue_closed",
  "ci_passed",
  "ci_failed",
  "release",
);
const history = object({
  id: string,
  timestamp: string,
  actor: string,
  action: string,
  oldValue: optional(string),
  newValue: optional(string),
});
const base = { id: string, isSynthetic: synthetic };
const config = object({
  rootFolderUrl: optional(string),
  agentWorkFolderId: optional(string),
  readableFolderIds: optional(list(string)),
  writableFolderIds: optional(list(string)),
  autoOrganizeFolderIds: optional(list(string)),
  workspaceId: optional(string),
  databaseId: optional(string),
  databaseName: optional(string),
  allowCreateTasks: optional(boolean),
  allowEditTasks: optional(boolean),
  installationId: optional(string),
  orgOrUser: optional(string),
  monitoredRepoIds: optional(list(string)),
  eventTriggers: optional(list(eventType)),
});
const drive = object({
  ...base,
  name: string,
  type: choice("file", "folder"),
  parentId: nullable(string),
  mimeType: string,
  projectId: optional(string),
  category: optional(
    choice(
      "contract",
      "invoice",
      "report",
      "evidence",
      "spreadsheet",
      "technical_doc",
      "financial_doc",
      "memo",
      "other",
    ),
  ),
  isOriginal: boolean,
  isProtected: boolean,
  derivedFromId: optional(string),
  content: optional(string),
  createdAt: string,
  modifiedAt: string,
  createdBy: choice("user", "agent", "system"),
});
const activity = object({
  ...base,
  title: string,
  description: string,
  projectId: string,
  assignee: string,
  priority,
  status: activityStatus,
  dueDate: nullable(string),
  evidenceIds: list(string),
  origin: choice("user", "agent", "github", "drive", "system"),
  history: list(history),
  createdAt: string,
  modifiedAt: string,
});
const evidence = object({
  ...base,
  projectId: string,
  claim: string,
  source: choice("github", "notion", "drive", "upload"),
  sourceRef: string,
  status: choice("supported", "pending", "disputed"),
  confidence: number,
  reason: string,
  generatedBy: string,
  relatedActivityId: optional(string),
  createdAt: string,
});
const activityPatch = object({
  title: optional(string),
  description: optional(string),
  assignee: optional(string),
  priority: optional(priority),
  status: optional(activityStatus),
  dueDate: optional(nullable(string)),
  evidenceIds: optional(list(string)),
});
function command(value: unknown): boolean {
  if (typeof value !== "object" || value === null || !("kind" in value))
    return false;
  const rules: Record<string, Rule> = {
    inspect: object({
      provider,
      operation: string,
      resourceId: string,
      projectId: optional(string),
    }),
    "drive.create": object({ item: drive }),
    "drive.copy": object({ sourceId: string, item: drive }),
    "drive.update": object({
      id: string,
      patch: object({
        name: optional(string),
        parentId: optional(string),
        content: optional(string),
      }),
    }),
    "activity.create": object({ activity }),
    "activity.update": object({ id: string, patch: activityPatch }),
    "activity.attach_evidence": object({ id: string, evidenceId: string }),
    "activity.annotate": object({ id: string, entry: string }),
    "evidence.create": object({ evidence }),
    review: object({ activityId: string, projectId: string }),
    "checklist.update": object({
      id: string,
      status: documentStatus,
      documentId: optional(string),
      validatedBy: optional(string),
    }),
  };
  return typeof value.kind === "string" && !!rules[value.kind]?.(value);
}
const step = object({
  id: string,
  sequence: number,
  label: string,
  description: string,
  tool: optional(string),
  status: runStatus,
  timestamp: string,
  result: optional(string),
  command: optional(command),
});
const project = object({
  ...base,
  identifier: string,
  name: string,
  description: string,
  objectives: string,
  startDate: string,
  endDate: string,
  responsible: string,
  status: choice("planning", "active", "on_hold", "completed", "cancelled"),
  team: list(string),
  activityIds: list(string),
  repoIds: list(string),
  driveFolderIds: list(string),
  evidenceIds: list(string),
  financialDocIds: list(string),
  reportIds: list(string),
  completeness: number,
  pendingItems: list(string),
  history: list(history),
});
const app = object({
  organization: object({
    ...base,
    name: string,
    cnpj: string,
    tenantId: string,
    taxYear: number,
  }),
  integrations: list(
    object({
      ...base,
      provider,
      label: string,
      description: string,
      status: choice("connected", "disconnected", "error"),
      connectedAt: nullable(string),
      config,
    }),
  ),
  driveItems: list(drive),
  activities: list(activity),
  evidence: list(evidence),
  projects: list(project),
  githubRepos: list(
    object({
      ...base,
      name: string,
      fullName: string,
      orgOrUser: string,
      projectId: optional(string),
      url: string,
    }),
  ),
  githubEvents: list(
    object({
      ...base,
      repoId: string,
      type: eventType,
      title: string,
      description: string,
      author: string,
      timestamp: string,
      url: string,
      projectId: optional(string),
    }),
  ),
  agentRuns: list(
    object({
      ...base,
      triggerEvent: string,
      triggerSource: string,
      module: choice(
        "documental",
        "technical",
        "financial",
        "compliance",
        "orchestrator",
      ),
      status: runStatus,
      steps: list(step),
      cursor: number,
      result: optional(string),
      error: optional(string),
      startedAt: string,
      completedAt: nullable(string),
      projectId: optional(string),
      correlationId: string,
    }),
  ),
  approvalRequests: list(
    object({
      ...base,
      runId: optional(string),
      stepId: optional(string),
      command: optional(command),
      class: choice("A0", "A1", "A2", "A3", "A4"),
      title: string,
      description: string,
      context: list(object({ label: string, value: string })),
      status: choice("pending", "approved", "rejected", "needs_revision"),
      requestedAt: string,
      resolvedAt: nullable(string),
      resolvedBy: nullable(string),
      resolutionNote: optional(string),
      projectId: optional(string),
    }),
  ),
  auditLogs: list(
    object({
      id: string,
      executionId: optional(string),
      eventOrigin: string,
      operation: string,
      resourceAffected: string,
      timestamp: string,
      result: string,
      actor: string,
      previousState: optional(string),
      newState: optional(string),
      policyApplied: optional(permission),
    }),
  ),
  permissionPolicies: list(
    object({
      id: string,
      provider,
      operation: string,
      label: string,
      description: string,
      level: permission,
      category: choice("read", "write_internal", "external", "formal"),
      projectId: optional(string),
      resourceId: optional(string),
    }),
  ),
  leiDoBemItems: list(
    object({
      id: string,
      type: string,
      label: string,
      status: documentStatus,
      projectId: string,
      documentId: optional(string),
      lastModified: optional(string),
      validatedBy: optional(string),
    }),
  ),
});
export function isAppState(value: unknown): value is AppState {
  return app(value);
}
export function validReferences(state: AppState): boolean {
  const projects = new Set(state.projects.map((p) => p.id));
  const resources = [
    ...state.driveItems,
    ...state.activities,
    ...state.evidence,
    ...state.githubRepos,
    ...state.githubEvents,
    ...state.agentRuns,
    ...state.approvalRequests,
    ...state.leiDoBemItems,
  ];
  if (resources.some((r) => r.projectId && !projects.has(r.projectId)))
    return false;
  if (
    state.integrations.length !== 3 ||
    new Set(state.integrations.map((i) => i.provider)).size !== 3
  )
    return false;
  if (
    state.driveItems.some(
      (d) =>
        d.parentId &&
        !state.driveItems.some(
          (p) => p.id === d.parentId && p.type === "folder",
        ),
    )
  )
    return false;
  if (
    state.agentRuns.some(
      (r) =>
        !Number.isInteger(r.cursor) ||
        r.cursor! < 0 ||
        r.cursor! > r.steps.length ||
        r.steps.some((s) => !s.command),
    )
  )
    return false;
  if (
    state.activities.some((a) =>
      a.evidenceIds.some(
        (id) =>
          !state.evidence.some(
            (e) => e.id === id && e.projectId === a.projectId,
          ),
      ),
    )
  )
    return false;
  return state.projects.length > 0;
}
