import type {
  AppState, Organization, Integration, DriveItem, Activity, GithubRepo,
  GithubEvent, Evidence, AgentRun, ApprovalRequest, AuditLog, Project,
  LeiDoBemDocumentItem, ActivityHistoryEntry,
} from "@/types";
import { seedPermissionPolicies } from "./permissionPolicies";

const now = new Date("2026-11-07T10:00:00-03:00");
const iso = (offsetMin: number) =>
  new Date(now.getTime() + offsetMin * 60000).toISOString();

// --- Organization ---
const organization: Organization = {
  id: "org-1",
  name: "Basho Tecnologia Ltda.",
  cnpj: "12.345.678/0001-90",
  tenantId: "11111111-1111-4111-8111-111111111111",
  taxYear: 2026,
  isSynthetic: true,
};

// --- Integrations ---
const integrations: Integration[] = [
  {
    id: "int-drive",
    provider: "google_drive",
    label: "Google Drive",
    description: "Gerenciamento documental e armazenamento de evidências",
    status: "disconnected",
    connectedAt: null,
    config: {},
    isSynthetic: true,
  },
  {
    id: "int-notion",
    provider: "notion",
    label: "Notion",
    description: "Gestão de projetos, atividades e tarefas",
    status: "disconnected",
    connectedAt: null,
    config: {},
    isSynthetic: true,
  },
  {
    id: "int-github",
    provider: "github",
    label: "GitHub",
    description: "Acompanhamento do desenvolvimento técnico",
    status: "disconnected",
    connectedAt: null,
    config: {},
    isSynthetic: true,
  },
];

// --- Drive Items (folders first, then files) ---
const driveItems: DriveItem[] = [
  // Root folder
  { id: "drive-folder-root", name: "Basho — Drive Principal", type: "folder", parentId: null, mimeType: "application/vnd.google-apps.folder", isOriginal: true, isProtected: true, createdAt: iso(-60000), modifiedAt: iso(-60000), createdBy: "system", isSynthetic: true },

  // Project folders
  { id: "drive-folder-pd001", name: "PD-001 — Plataforma Agentiva", type: "folder", parentId: "drive-folder-root", mimeType: "application/vnd.google-apps.folder", projectId: "pd-001", isOriginal: true, isProtected: false, createdAt: iso(-50000), modifiedAt: iso(-5000), createdBy: "system", isSynthetic: true },
  { id: "drive-folder-pd002", name: "PD-002 — Motor de Inferência", type: "folder", parentId: "drive-folder-root", mimeType: "application/vnd.google-apps.folder", projectId: "pd-002", isOriginal: true, isProtected: false, createdAt: iso(-50000), modifiedAt: iso(-5000), createdBy: "system", isSynthetic: true },

  // Subfolders PD-001
  { id: "drive-folder-pd001-contracts", name: "Contratos", type: "folder", parentId: "drive-folder-pd001", mimeType: "application/vnd.google-apps.folder", projectId: "pd-001", isOriginal: true, isProtected: false, createdAt: iso(-49000), modifiedAt: iso(-49000), createdBy: "system", isSynthetic: true },
  { id: "drive-folder-pd001-invoices", name: "Notas Fiscais", type: "folder", parentId: "drive-folder-pd001", mimeType: "application/vnd.google-apps.folder", projectId: "pd-001", isOriginal: true, isProtected: false, createdAt: iso(-49000), modifiedAt: iso(-49000), createdBy: "system", isSynthetic: true },
  { id: "drive-folder-pd001-reports", name: "Relatórios Técnicos", type: "folder", parentId: "drive-folder-pd001", mimeType: "application/vnd.google-apps.folder", projectId: "pd-001", isOriginal: true, isProtected: false, createdAt: iso(-49000), modifiedAt: iso(-49000), createdBy: "system", isSynthetic: true },
  { id: "drive-folder-pd001-evidence", name: "Evidências", type: "folder", parentId: "drive-folder-pd001", mimeType: "application/vnd.google-apps.folder", projectId: "pd-001", isOriginal: true, isProtected: false, createdAt: iso(-49000), modifiedAt: iso(-49000), createdBy: "system", isSynthetic: true },
  { id: "drive-folder-pd001-agent-work", name: "Trabalho dos Agentes", type: "folder", parentId: "drive-folder-pd001", mimeType: "application/vnd.google-apps.folder", projectId: "pd-001", isOriginal: false, isProtected: false, createdAt: iso(-49000), modifiedAt: iso(-49000), createdBy: "agent", isSynthetic: true },

  // Subfolders PD-002
  { id: "drive-folder-pd002-reports", name: "Relatórios Técnicos", type: "folder", parentId: "drive-folder-pd002", mimeType: "application/vnd.google-apps.folder", projectId: "pd-002", isOriginal: true, isProtected: false, createdAt: iso(-49000), modifiedAt: iso(-49000), createdBy: "system", isSynthetic: true },

  // Files — Contracts (protected originals)
  { id: "drive-file-contract-001", name: "Contrato de P&D — PD-001.pdf", type: "file", parentId: "drive-folder-pd001-contracts", mimeType: "application/pdf", category: "contract", projectId: "pd-001", isOriginal: true, isProtected: true, size: "1.2 MB", createdAt: iso(-48000), modifiedAt: iso(-48000), createdBy: "system", isSynthetic: true },

  // Files — Invoices (protected originals)
  { id: "drive-file-invoice-001", name: "NF-e 000123456 — R$ 24.000,00.pdf", type: "file", parentId: "drive-folder-pd001-invoices", mimeType: "application/pdf", category: "invoice", projectId: "pd-001", isOriginal: true, isProtected: true, size: "340 KB", createdAt: iso(-30000), modifiedAt: iso(-30000), createdBy: "system", isSynthetic: true },
  { id: "drive-file-invoice-002", name: "NF-e 000123457 — R$ 8.500,00.pdf", type: "file", parentId: "drive-folder-pd001-invoices", mimeType: "application/pdf", category: "invoice", projectId: "pd-001", isOriginal: true, isProtected: true, size: "290 KB", createdAt: iso(-25000), modifiedAt: iso(-25000), createdBy: "system", isSynthetic: true },

  // Files — Spreadsheets
  { id: "drive-file-spreadsheet-001", name: "Planilha de Despesas PD-001.xlsx", type: "file", parentId: "drive-folder-pd001-invoices", mimeType: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", category: "spreadsheet", projectId: "pd-001", isOriginal: true, isProtected: true, size: "56 KB", createdAt: iso(-28000), modifiedAt: iso(-28000), createdBy: "system", isSynthetic: true },

  // Files — Reports (one original, one derived)
  { id: "drive-file-pd001-report-001", name: "Relatório Técnico Mensal — Outubro.pdf", type: "file", parentId: "drive-folder-pd001-reports", mimeType: "application/pdf", category: "report", projectId: "pd-001", isOriginal: true, isProtected: true, size: "890 KB", createdAt: iso(-3000), modifiedAt: iso(-3000), createdBy: "user", isSynthetic: true },

  // Files — Evidence
  { id: "drive-file-pd001-evidence-001", name: "Resultado do Experimento — Motor de Orquestração.md", type: "file", parentId: "drive-folder-pd001-evidence", mimeType: "text/markdown", category: "evidence", projectId: "pd-001", isOriginal: false, isProtected: false, size: "12 KB", content: "# Resultado do Experimento\n\nTeste de validação do orquestrador determinístico...",
    createdAt: iso(-4000), modifiedAt: iso(-4000), createdBy: "agent", isSynthetic: true },
];

// --- GitHub Repos ---
const githubRepos: GithubRepo[] = [
  { id: "gh-repo-1", name: "basho-platform", fullName: "basho-tech/basho-platform", orgOrUser: "basho-tech", projectId: "pd-001", url: "https://github.com/basho-tech/basho-platform", isSynthetic: true },
  { id: "gh-repo-2", name: "inference-engine", fullName: "basho-tech/inference-engine", orgOrUser: "basho-tech", projectId: "pd-002", url: "https://github.com/basho-tech/inference-engine", isSynthetic: true },
];

// --- GitHub Events (initial seed — empty, user will trigger them) ---
const githubEvents: GithubEvent[] = [];

// --- Activities ---
const mkHistory = (entries: Array<[string, string, string, string, string?]>): ActivityHistoryEntry[] =>
  entries.map(([id, ts, actor, action, field]) => ({
    id: `hist-${id}`,
    timestamp: ts,
    actor,
    action: action.split("|")[0],
    field: field?.split("|")[0],
    oldValue: action.split("|")[1],
    newValue: action.split("|")[2],
  }));

const activities: Activity[] = [
  {
    id: "act-1",
    title: "Implementar orquestrador determinístico de fluxos",
    description: "Desenvolver o motor de orquestração que coordena agentes documental, técnico, financeiro e conformidade. Estado persistente por execução, contratos tipados entre etapas.",
    projectId: "pd-001",
    assignee: "Vitor Mendes",
    priority: "high",
    status: "in_progress",
    dueDate: iso(4320),
    evidenceIds: [],
    origin: "user",
    history: mkHistory([
      ["act-1-h1", iso(-20000), "Vitor Mendes", "Tarefa criada||"],
      ["act-1-h2", iso(-5000), "Agente Técnico", "Status alterado|todo|in_progress"],
    ]),
    createdAt: iso(-20000),
    modifiedAt: iso(-5000),
    isSynthetic: true,
  },
  {
    id: "act-2",
    title: "Configar integração com GitHub App",
    description: "Instalar GitHub App fictícia, selecionar repositórios monitorados e associar ao projeto PD-001.",
    projectId: "pd-001",
    assignee: "Vitor Mendes",
    priority: "medium",
    status: "done",
    dueDate: iso(-1440),
    evidenceIds: [],
    origin: "user",
    history: mkHistory([["act-2-h1", iso(-15000), "Vitor Mendes", "Tarefa criada||"], ["act-2-h2", iso(-3000), "Vitor Mendes", "Status alterado|in_progress|done"]]),
    createdAt: iso(-15000),
    modifiedAt: iso(-3000),
    isSynthetic: true,
  },
  {
    id: "act-3",
    title: "Validar gates de liberação de release",
    description: "Verificar que todos os gates determinísticos estão satisfeitos: empresa configurada, projetos com novidade/barreira/método, valores reconciliados, horas de registros confiáveis, citações acessíveis, zero A3.",
    projectId: "pd-001",
    assignee: "Ana Costa",
    priority: "urgent",
    status: "review",
    dueDate: iso(2880),
    evidenceIds: [],
    origin: "user",
    history: mkHistory([["act-3-h1", iso(-8000), "Ana Costa", "Tarefa criada||"], ["act-3-h2", iso(-2000), "Agente de Conformidade", "Status alterado|todo|review"]]),
    createdAt: iso(-8000),
    modifiedAt: iso(-2000),
    isSynthetic: true,
  },
  {
    id: "act-4",
    title: "Documentar barreiras tecnológicas do motor de inferência",
    description: "Relatar incertezas tecnológicas, hipóteses testadas e resultados dos experimentos de inferência.",
    projectId: "pd-002",
    assignee: "Carlos Silva",
    priority: "high",
    status: "todo",
    dueDate: iso(5760),
    evidenceIds: [],
    origin: "user",
    history: mkHistory([["act-4-h1", iso(-6000), "Carlos Silva", "Tarefa criada||"]]),
    createdAt: iso(-6000),
    modifiedAt: iso(-6000),
    isSynthetic: true,
  },
];

// --- Evidence ---
const evidence: Evidence[] = [];

// --- Agent Runs / Approvals / Audit (empty initially) ---
const agentRuns: AgentRun[] = [];
const approvalRequests: ApprovalRequest[] = [];
const auditLogs: AuditLog[] = [];

// --- Projects ---
const projects: Project[] = [
  {
    id: "pd-001",
    identifier: "PD-001",
    name: "Plataforma Agentiva de Gestão de PD&I",
    description: "Plataforma inteligente para gestão de projetos de Pesquisa, Desenvolvimento e Inovação com conformidade da Lei do Bem, agentes autônomos e rastreabilidade de evidências.",
    objectives: "Construir uma plataforma que automatize a coleta de evidências, organização documental e preparação do dossiê do FORMP&D, com intervenção humana por exceção.",
    startDate: "2026-07-01",
    endDate: "2027-06-30",
    status: "active",
    responsible: "Vitor Mendes",
    team: ["Vitor Mendes", "Ana Costa", "Carlos Silva"],
    activityIds: ["act-1", "act-2", "act-3"],
    repoIds: ["gh-repo-1"],
    driveFolderIds: ["drive-folder-pd001"],
    evidenceIds: [],
    financialDocIds: ["drive-file-contract-001", "drive-file-invoice-001", "drive-file-invoice-002", "drive-file-spreadsheet-001"],
    reportIds: ["drive-file-pd001-report-001"],
    completeness: 65,
    pendingItems: [
      "Validar gates de liberação de release",
      "Completar registro de experimentos do motor de orquestração",
      "Aguardar critério de rateio do contrato misto NF-123456",
    ],
    history: [
      { id: "ph-1", timestamp: iso(-20000), actor: "Vitor Mendes", action: "Projeto criado" },
      { id: "ph-2", timestamp: iso(-10000), actor: "Sistema", action: "Repositório basho-platform vinculado" },
      { id: "ph-3", timestamp: iso(-5000), actor: "Agente Técnico", action: "Evidência técnica registrada" },
    ],
    isSynthetic: true,
  },
  {
    id: "pd-002",
    identifier: "PD-002",
    name: "Motor de Inferência para Análise Documental",
    description: "Desenvolvimento de motor de inferência para análise e extração de informações de documentos técnicos e financeiros.",
    objectives: "Criar capacidade de extrair e relacionar informações de documentos heterogêneos mantendo rastreabilidade e proveniência.",
    startDate: "2026-09-01",
    endDate: "2027-03-31",
    status: "active",
    responsible: "Carlos Silva",
    team: ["Carlos Silva", "Ana Costa"],
    activityIds: ["act-4"],
    repoIds: ["gh-repo-2"],
    driveFolderIds: ["drive-folder-pd002"],
    evidenceIds: [],
    financialDocIds: [],
    reportIds: [],
    completeness: 30,
    pendingItems: [
      "Documentar barreiras tecnológicas",
      "Registrar experimentos preliminares",
    ],
    history: [
      { id: "ph-4", timestamp: iso(-10000), actor: "Carlos Silva", action: "Projeto criado" },
    ],
    isSynthetic: true,
  },
];

// --- Lei do Bem Document Items ---
const leiDoBemItems: LeiDoBemDocumentItem[] = [
  { id: "lb-1", type: "technical_description", label: "Descrição técnica do projeto", status: "validated", documentId: "drive-file-pd001-report-001", projectId: "pd-001", lastModified: iso(-3000), validatedBy: "Ana Costa" },
  { id: "lb-2", type: "objectives", label: "Objetivos e desafios tecnológicos", status: "present", projectId: "pd-001", lastModified: iso(-5000) },
  { id: "lb-3", type: "tech_uncertainties", label: "Incertezas tecnológicas", status: "draft", projectId: "pd-001" },
  { id: "lb-4", type: "rd_activities", label: "Atividades de pesquisa e desenvolvimento", status: "present", projectId: "pd-001", documentId: "drive-file-pd001-evidence-001", lastModified: iso(-4000) },
  { id: "lb-5", type: "experiments", label: "Experimentações e testes", status: "pending_review", projectId: "pd-001" },
  { id: "lb-6", type: "results", label: "Resultados técnicos", status: "draft", projectId: "pd-001" },
  { id: "lb-7", type: "hr_resources", label: "Recursos humanos envolvidos", status: "absent", projectId: "pd-001" },
  { id: "lb-8", type: "expenses", label: "Despesas e documentos comprobatórios", status: "present", projectId: "pd-001", documentId: "drive-file-spreadsheet-001", lastModified: iso(-28000) },
  { id: "lb-9", type: "accompanyment_reports", label: "Relatórios de acompanhamento", status: "present", projectId: "pd-001", documentId: "drive-file-pd001-report-001", lastModified: iso(-3000) },
  { id: "lb-10", type: "documentary_evidence", label: "Evidências documentais", status: "pending_review", projectId: "pd-001" },
  { id: "lb-11", type: "validations", label: "Pendências e validações", status: "absent", projectId: "pd-001" },

  { id: "lb-12", type: "technical_description", label: "Descrição técnica do projeto", status: "draft", projectId: "pd-002" },
  { id: "lb-13", type: "objectives", label: "Objetivos e desafios tecnológicos", status: "draft", projectId: "pd-002" },
  { id: "lb-14", type: "tech_uncertainties", label: "Incertezas tecnológicas", status: "absent", projectId: "pd-002" },
  { id: "lb-15", type: "rd_activities", label: "Atividades de pesquisa e desenvolvimento", status: "absent", projectId: "pd-002" },
  { id: "lb-16", type: "experiments", label: "Experimentações e testes", status: "absent", projectId: "pd-002" },
  { id: "lb-17", type: "results", label: "Resultados técnicos", status: "absent", projectId: "pd-002" },
  { id: "lb-18", type: "hr_resources", label: "Recursos humanos envolvidos", status: "absent", projectId: "pd-002" },
  { id: "lb-19", type: "expenses", label: "Despesas e documentos comprobatórios", status: "absent", projectId: "pd-002" },
  { id: "lb-20", type: "accompanyment_reports", label: "Relatórios de acompanhamento", status: "absent", projectId: "pd-002" },
  { id: "lb-21", type: "documentary_evidence", label: "Evidências documentais", status: "absent", projectId: "pd-002" },
  { id: "lb-22", type: "validations", label: "Pendências e validações", status: "absent", projectId: "pd-002" },
];

// --- Export initial state ---
export function createInitialState(): AppState {
  return structuredClone({
    organization,
    integrations,
    driveItems,
    activities,
    githubRepos,
    githubEvents,
    evidence,
    agentRuns,
    approvalRequests,
    auditLogs,
    permissionPolicies: seedPermissionPolicies.map((p) => ({ ...p })),
    projects,
    leiDoBemItems,
  });
}
