// ============================================================
// Basho — Domain Types
// Centralized type definitions for the simulated PD&I platform
// ============================================================

// --- IDs ---
export type ID = string;

// --- Organization ---
export interface Organization {
  id: ID;
  name: string;
  cnpj: string;
  tenantId: string;
  taxYear: number;
  isSynthetic: boolean;
}

// --- Integrations ---
export type IntegrationProvider = "google_drive" | "notion" | "github";

export type IntegrationStatus = "connected" | "disconnected" | "error";

export interface Integration {
  id: ID;
  provider: IntegrationProvider;
  label: string;
  description: string;
  status: IntegrationStatus;
  connectedAt: string | null;
  config: IntegrationConfig;
  isSynthetic: boolean;
}

export interface IntegrationConfig {
  // Google Drive
  rootFolderUrl?: string;
  agentWorkFolderId?: string;
  writableFolderIds?: ID[];
  readableFolderIds?: ID[];
  autoOrganizeFolderIds?: ID[];
  // Notion
  workspaceId?: string;
  databaseId?: ID;
  databaseName?: string;
  allowCreateTasks?: boolean;
  allowEditTasks?: boolean;
  // GitHub
  installationId?: string;
  orgOrUser?: string;
  monitoredRepoIds?: ID[];
  eventTriggers?: string[];
}

// --- Drive / Documents ---
export type DocumentCategory =
  | "contract"
  | "invoice"
  | "report"
  | "evidence"
  | "spreadsheet"
  | "technical_doc"
  | "financial_doc"
  | "memo"
  | "other";

export type DocumentStatus =
  | "present"
  | "absent"
  | "draft"
  | "pending_review"
  | "validated";

export interface DriveItem {
  id: ID;
  name: string;
  type: "folder" | "file";
  parentId: ID | null;
  mimeType: string;
  category?: DocumentCategory;
  projectId?: ID;
  isOriginal: boolean;
  isProtected: boolean;
  derivedFromId?: ID;
  size?: string;
  content?: string;
  createdAt: string;
  modifiedAt: string;
  createdBy: "user" | "agent" | "system";
  isSynthetic: boolean;
}

// --- Notion / Activities ---
export type ActivityStatus =
  | "todo"
  | "in_progress"
  | "review"
  | "done"
  | "blocked";
export type ActivityPriority = "low" | "medium" | "high" | "urgent";
export type ActivityOrigin = "user" | "agent" | "github" | "drive" | "system";

export interface Activity {
  id: ID;
  externalId?: string;
  title: string;
  description: string;
  projectId: ID;
  assignee: string;
  priority: ActivityPriority;
  status: ActivityStatus;
  dueDate: string | null;
  evidenceIds: ID[];
  origin: ActivityOrigin;
  history: ActivityHistoryEntry[];
  createdAt: string;
  modifiedAt: string;
  isSynthetic: boolean;
}

export interface ActivityHistoryEntry {
  id: ID;
  timestamp: string;
  actor: string;
  action: string;
  field?: string;
  oldValue?: string;
  newValue?: string;
}

// --- GitHub ---
export type GithubEventType =
  | "commit"
  | "pr_merged"
  | "pr_opened"
  | "issue_opened"
  | "issue_closed"
  | "ci_passed"
  | "ci_failed"
  | "release";

export interface GithubRepo {
  id: ID;
  name: string;
  fullName: string;
  orgOrUser: string;
  projectId?: ID;
  url: string;
  isSynthetic: boolean;
}

export interface GithubEvent {
  id: ID;
  repoId: ID;
  type: GithubEventType;
  title: string;
  description: string;
  author: string;
  sha?: string;
  url: string;
  timestamp: string;
  projectId?: ID;
  isSynthetic: boolean;
}

// --- Evidence ---
export type EvidenceStatus = "supported" | "pending" | "disputed";

export interface Evidence {
  id: ID;
  projectId: ID;
  claim: string;
  source: "github" | "notion" | "drive" | "upload";
  sourceRef: string;
  locator?: string;
  status: EvidenceStatus;
  confidence: number;
  reason: string;
  generatedBy: string;
  relatedActivityId?: ID;
  createdAt: string;
  isSynthetic: boolean;
}

// --- Agent / Operations ---
export type AgentModule =
  | "documental"
  | "technical"
  | "financial"
  | "compliance"
  | "orchestrator";

export interface AgentDefinition {
  id: ID;
  module: AgentModule;
  name: string;
  description: string;
  isActive: boolean;
}

export type RunStatus =
  | "waiting"
  | "running"
  | "completed"
  | "failed"
  | "awaiting_approval"
  | "blocked_by_policy";

export interface AgentRun {
  id: ID;
  triggerEvent: string;
  triggerSource: string;
  module: AgentModule;
  status: RunStatus;
  steps: AgentStep[];
  result?: string;
  error?: string;
  startedAt: string;
  completedAt: string | null;
  projectId?: ID;
  correlationId: string;
  scenario?: ScenarioId;
  sourceEventId?: string;
  cursor?: number;
  isSynthetic: boolean;
}

export interface AgentStep {
  id: ID;
  sequence: number;
  label: string;
  description: string;
  tool?: string;
  status: RunStatus;
  result?: string;
  resourceAffected?: string;
  policyApplied?: PermissionLevel;
  timestamp: string;
  command?: SimulationCommand;
}

export interface AgentAction {
  id: ID;
  runId: ID;
  stepId: ID;
  type: string;
  target: string;
  status: "executed" | "blocked" | "pending_approval";
  details: string;
  timestamp: string;
}

// --- Approvals ---
export type ApprovalStatus =
  | "pending"
  | "approved"
  | "rejected"
  | "needs_revision";
export type ApprovalClass = "A0" | "A1" | "A2" | "A3" | "A4";

export interface ApprovalRequest {
  id: ID;
  runId?: ID;
  class: ApprovalClass;
  title: string;
  description: string;
  context: ApprovalContext[];
  status: ApprovalStatus;
  requestedAt: string;
  resolvedAt: string | null;
  resolvedBy: string | null;
  resolutionNote?: string;
  command?: SimulationCommand;
  stepId?: string;
  projectId?: ID;
  isSynthetic: boolean;
}

export interface ApprovalContext {
  label: string;
  value: string;
}

// --- Audit ---
export interface AuditLog {
  id: ID;
  executionId?: string;
  eventOrigin: string;
  operation: string;
  resourceAffected: string;
  previousState?: string;
  newState?: string;
  timestamp: string;
  result: string;
  justification?: string;
  policyApplied?: PermissionLevel;
  actor: string;
  correlationId?: string;
}

// --- Permissions ---
export type PermissionLevel = "automatic" | "requires_approval" | "blocked";

export interface PermissionPolicy {
  id: ID;
  provider: IntegrationProvider;
  operation: string;
  label: string;
  description: string;
  level: PermissionLevel;
  category: "read" | "write_internal" | "external" | "formal";
  projectId?: ID;
  resourceId?: ID;
}

// --- Projects ---
export type ProjectStatus =
  | "planning"
  | "active"
  | "on_hold"
  | "completed"
  | "cancelled";

export interface Project {
  id: ID;
  identifier: string;
  name: string;
  description: string;
  objectives: string;
  startDate: string;
  endDate: string;
  status: ProjectStatus;
  responsible: string;
  team: string[];
  activityIds: ID[];
  repoIds: ID[];
  driveFolderIds: ID[];
  evidenceIds: ID[];
  financialDocIds: ID[];
  reportIds: ID[];
  completeness: number;
  pendingItems: string[];
  history: ProjectHistoryEntry[];
  isSynthetic: boolean;
}

export interface ProjectHistoryEntry {
  id: ID;
  timestamp: string;
  actor: string;
  action: string;
}

// --- Lei do Bem / Document Module ---
export interface LeiDoBemDocumentItem {
  id: ID;
  type: string;
  label: string;
  status: DocumentStatus;
  documentId?: ID;
  projectId: ID;
  lastModified?: string;
  validatedBy?: string;
}

// --- Workflow Simulation ---
export type ScenarioId = "A" | "B" | "C";

export interface ScenarioDefinition {
  id: ScenarioId;
  title: string;
  description: string;
  triggerLabel: string;
}

// --- Global State Shape ---
export interface AppState {
  organization: Organization;
  integrations: Integration[];
  driveItems: DriveItem[];
  activities: Activity[];
  githubRepos: GithubRepo[];
  githubEvents: GithubEvent[];
  evidence: Evidence[];
  agentRuns: AgentRun[];
  approvalRequests: ApprovalRequest[];
  auditLogs: AuditLog[];
  permissionPolicies: PermissionPolicy[];
  projects: Project[];
  leiDoBemItems: LeiDoBemDocumentItem[];
}

// Serializable commands: boundary for the UI, simulator and future adapters.
export type SimulationCommand =
  | {
      kind: "inspect";
      provider: IntegrationProvider;
      operation: string;
      resourceId: ID;
      projectId?: ID;
    }
  | { kind: "drive.create"; item: DriveItem }
  | { kind: "drive.copy"; sourceId: ID; item: DriveItem }
  | {
      kind: "drive.update";
      id: ID;
      patch: { name?: string; parentId?: ID; content?: string };
    }
  | { kind: "activity.create"; activity: Activity }
  | { kind: "activity.attach_evidence"; id: ID; evidenceId: ID }
  | { kind: "activity.annotate"; id: ID; entry: string }
  | {
      kind: "activity.update";
      id: ID;
      patch: Partial<
        Pick<
          Activity,
          | "title"
          | "description"
          | "assignee"
          | "priority"
          | "status"
          | "dueDate"
          | "evidenceIds"
        >
      >;
    }
  | { kind: "evidence.create"; evidence: Evidence }
  | { kind: "review"; activityId: ID; projectId: ID }
  | {
      kind: "checklist.update";
      id: ID;
      status: DocumentStatus;
      documentId?: ID;
      validatedBy?: string;
    };
export interface ExternalResource {
  id: ID;
  provider: IntegrationProvider;
  projectId?: ID;
  externalId: string;
  isSynthetic: boolean;
}
export type Document = DriveItem & { type: "file" };
export type Folder = DriveItem & { type: "folder" };
export interface SimulationResult {
  state: AppState;
  outcome: "executed" | "blocked" | "pending_approval";
  message: string;
}
