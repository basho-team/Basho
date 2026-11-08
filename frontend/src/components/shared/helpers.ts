import type { AppState, DriveItem } from "@/types";

export function formatDate(iso: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso.length === 10 ? `${iso}T12:00:00-03:00` : iso);
  return d.toLocaleDateString("pt-BR", {
    timeZone: "America/Fortaleza",
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function formatDateShort(iso: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso);
  return d.toLocaleDateString("pt-BR", {
    timeZone: "America/Fortaleza",
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
  });
}

export function timeAgo(iso: string | null): string {
  if (!iso) return "—";
  const now = Date.now();
  const then = new Date(iso).getTime();
  const diff = now - then;
  const min = Math.floor(diff / 60000);
  const hours = Math.floor(min / 60);
  const days = Math.floor(hours / 24);
  if (days > 0) return `há ${days}d`;
  if (hours > 0) return `há ${hours}h`;
  if (min > 0) return `há ${min}min`;
  return "agora";
}

export function getChildren(
  items: DriveItem[],
  parentId: string | null,
): DriveItem[] {
  const folders = items
    .filter((i) => i.parentId === parentId && i.type === "folder")
    .sort((a, b) => a.name.localeCompare(b.name));
  const files = items
    .filter((i) => i.parentId === parentId && i.type === "file")
    .sort((a, b) => a.name.localeCompare(b.name));
  return [...folders, ...files];
}

export function getDescendantIds(
  items: DriveItem[],
  folderId: string,
): string[] {
  const result: string[] = [folderId];
  const queue = [folderId];
  while (queue.length > 0) {
    const current = queue.shift()!;
    const children = items.filter((i) => i.parentId === current);
    for (const child of children) {
      result.push(child.id);
      if (child.type === "folder") queue.push(child.id);
    }
  }
  return result;
}

export function getProjectName(state: AppState, projectId?: string): string {
  if (!projectId) return "—";
  const project = state.projects.find((p) => p.id === projectId);
  return project ? `${project.identifier} — ${project.name}` : "—";
}

export function getProjectIdentifier(
  state: AppState,
  projectId?: string,
): string {
  if (!projectId) return "—";
  const project = state.projects.find((p) => p.id === projectId);
  return project?.identifier ?? "—";
}

export function getRepoName(state: AppState, repoId: string): string {
  const repo = state.githubRepos.find((r) => r.id === repoId);
  return repo?.fullName ?? repoId;
}

export const CATEGORY_LABELS: Record<string, string> = {
  contract: "Contrato",
  invoice: "Nota Fiscal",
  report: "Relatório",
  evidence: "Evidência",
  spreadsheet: "Planilha",
  technical_doc: "Documento Técnico",
  financial_doc: "Documento Financeiro",
  memo: "Memorando",
  other: "Outro",
};

export const PRIORITY_LABELS: Record<string, string> = {
  low: "Baixa",
  medium: "Média",
  high: "Alta",
  urgent: "Urgente",
};

export const ORIGIN_LABELS: Record<string, string> = {
  user: "Usuário",
  agent: "Agente",
  github: "GitHub",
  drive: "Drive",
  system: "Sistema",
};

export const MODULE_LABELS: Record<string, string> = {
  documental: "Documental",
  technical: "Técnico",
  financial: "Financeiro",
  compliance: "Conformidade",
  orchestrator: "Orquestrador",
};

export const PROVIDER_LABELS: Record<string, string> = {
  google_drive: "Google Drive",
  notion: "Notion",
  github: "GitHub",
};
