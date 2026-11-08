import "server-only";
import type { DemoUser } from "@/lib/auth/shared";
import type { IntegrationOverview, IntegrationProvider } from "@/lib/integrations/shared";
import { DataSourceError } from "@/lib/data/source";

const CONFIG = {
  github: { name: "GitHub", implementation: "Conector disponível no backend. Esta prévia usa commits e PRs fictícios." },
  notion: { name: "Notion", implementation: "Prévia de páginas fictícias. Conector real e OAuth ainda não implementados." },
  drive: { name: "Google Drive", implementation: "Prévia de arquivos fictícios. Conector real e OAuth ainda não implementados." },
};
const SOURCES = [
  { provider: "github", id: "gh-ana-42", ownerId: "p-ana", title: "PR #42 · Calibração adaptativa", locator: "lumen-demo/calibra#42", revision: "a1f3c9e", excerpt: "Experimento em bancada: melhora observada, abaixo da meta.", isSynthetic: true },
  { provider: "github", id: "gh-bruno-9f", ownerId: "p-bruno", title: "Pipeline de coleta", locator: "lumen-demo/calibra@9f10b44", revision: "9f10b44", excerpt: "Integração da coleta ? bancada de calibração.", isSynthetic: true },
  { provider: "notion", id: "nt-ana-ensaios", ownerId: "p-ana", title: "Caderno de ensaios de Ana", locator: "notion-demo/ensaios-ana", revision: "v2", excerpt: "Registro de hipóteses, dúvidas e resultado negativo do experimento.", isSynthetic: true },
  { provider: "notion", id: "nt-bruno-s42", ownerId: "p-bruno", title: "Diário de bancada · semana 42", locator: "notion-demo/diario-bancada-s42", revision: "v3", excerpt: "Ensaios na bancada B e acompanhamento da deriva térmica.", isSynthetic: true },
  { provider: "drive", id: "gd-ana-relatorio", ownerId: "p-ana", title: "Relatório técnico de Ana", locator: "drive-demo/relatorios/ana-outubro.pdf", revision: "v1", excerpt: "Cópia sintética do relatório técnico do período.", isSynthetic: true },
  { provider: "drive", id: "gd-bruno-relatorio", ownerId: "p-bruno", title: "Relatório técnico de Bruno", locator: "drive-demo/relatorios/bruno-outubro.pdf", revision: "v2", excerpt: "Cópia sintética do relatório com fontes e lacunas.", isSynthetic: true },
  { provider: "drive", id: "gd-nf1023", ownerId: null, title: "NF 1023 e comprovante", locator: "drive-demo/financeiro/nf-1023.pdf", revision: "v1", excerpt: "Documento fictício com alocação ainda pendente de justificativa.", isSynthetic: true },
] as const;
type PreviewState = { enabled: boolean; checkedAt: string | null };
const previewGlobal = globalThis as typeof globalThis & { bashoIntegrationPreviews?: Record<IntegrationProvider, PreviewState> };
function state() {
  return previewGlobal.bashoIntegrationPreviews ??= {
    github: { enabled: true, checkedAt: null }, notion: { enabled: true, checkedAt: null }, drive: { enabled: true, checkedAt: null },
  };
}

export function integrationOverview(user: DemoUser): IntegrationOverview {
  return { mode: "demo", integrations: (Object.keys(CONFIG) as IntegrationProvider[]).map(provider => ({
    provider, ...CONFIG[provider], ...state()[provider], canConfigure: user.role === "manager",
    sources: state()[provider].enabled ? SOURCES.filter(source => source.provider === provider
      && (user.role !== "researcher" || source.ownerId === user.personId)).map(source => ({ ...source })) : [],
  })) };
}

export function integrationAction(user: DemoUser, provider: IntegrationProvider, action: "verify" | "sync" | "enable" | "disable"): IntegrationOverview {
  if (action !== "verify" && user.role !== "manager") {
    throw new DataSourceError({ code: "FORBIDDEN", message: "Só o gerente configura ou atualiza as prévias.", retryable: false, correlation_id: "demo-local" });
  }
  const current = state()[provider];
  if (action === "enable" || action === "disable") current.enabled = action === "enable";
  if (action === "verify" || action === "sync") {
    if (!current.enabled) throw new DataSourceError({ code: "DISABLED", message: "A prévia foi desativada pelo gerente.", retryable: false, correlation_id: "demo-local" });
    current.checkedAt = new Date().toISOString();
  }
  return integrationOverview(user);
}
