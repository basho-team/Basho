/**
 * Contrato de links autorizados e publicações (ADR-0010), seguro para o cliente: sem env nem
 * segredos. O navegador só declara o papel da demonstração; o BFF injeta a identidade.
 */
import { z } from "zod";
import { BFF_BASE } from "@/lib/bff/contract";

const Uuid = z.uuid();
const Timestamp = z.iso.datetime({ offset: true });
const seg = encodeURIComponent;

export const MAX_LINK_LENGTH = 2048;

export const integrationPaths = {
  config: () => `${BFF_BASE}/integrations/config`,
  links: (projectId: string) => `${BFF_BASE}/projects/${seg(projectId)}/links`,
  link: (projectId: string, linkId: string) => `${BFF_BASE}/projects/${seg(projectId)}/links/${seg(linkId)}`,
  publications: (projectId: string) => `${BFF_BASE}/projects/${seg(projectId)}/publications`,
  generate: (projectId: string) => `${BFF_BASE}/projects/${seg(projectId)}/generate`,
  run: (runId: string) => `${BFF_BASE}/agent-runs/${seg(runId)}`,
};

export const LinkKindSchema = z.enum(["github_repo", "drive_folder", "notion_page"]);
export type LinkKind = z.infer<typeof LinkKindSchema>;

export const LinkSchema = z.object({
  id: Uuid,
  project_id: Uuid,
  kind: LinkKindSchema,
  url: z.string(),
  display_name: z.string(),
  status: z.enum(["active", "revoked"]),
  last_check_at: Timestamp.nullable(),
  created_at: Timestamp,
});
export const LinksSchema = z.array(LinkSchema);
export type ProjectLink = z.infer<typeof LinkSchema>;

export const PublicationStatusSchema = z.enum(["queued", "running", "published", "failed"]);
export type PublicationStatus = z.infer<typeof PublicationStatusSchema>;

export const PublicationSchema = z.object({
  id: Uuid,
  project_id: Uuid,
  link_id: Uuid,
  link_kind: LinkKindSchema.nullable(),
  artifact_id: Uuid,
  title: z.string(),
  status: PublicationStatusSchema,
  attempts: z.number().int().nonnegative(),
  external_url: z.string().nullable(),
  error_code: z.string().nullable(),
  updated_at: Timestamp,
});
export const PublicationsSchema = z.object({ queued: z.number().int().nonnegative(), items: z.array(PublicationSchema) });
export type Publication = z.infer<typeof PublicationSchema>;
export type Publications = z.infer<typeof PublicationsSchema>;

export const IntegrationsConfigSchema = z.object({
  drive: z.boolean(),
  notion: z.boolean(),
  github: z.boolean(),
  google_service_account_email: z.string().nullable(),
});
export type IntegrationsConfig = z.infer<typeof IntegrationsConfigSchema>;

export const RunStatusSchema = z.enum(["queued", "running", "awaiting_input", "completed", "failed"]);
export type RunStatus = z.infer<typeof RunStatusSchema>;

/** Run do agente (`AgentRunOut`), só com o que a tela usa. */
export const AgentRunSchema = z.object({
  id: Uuid,
  project_id: Uuid,
  status: RunStatusSchema,
  attempts: z.number().int().nonnegative(),
  max_attempts: z.number().int().positive(),
  error: z.object({ code: z.string(), message: z.string(), retryable: z.boolean() }).nullable(),
  artifact_status: z.string().nullable(),
  updated_at: Timestamp,
});
export type AgentRun = z.infer<typeof AgentRunSchema>;

export const BffLinkRequestSchema = z.strictObject({ url: z.string().trim().min(8).max(MAX_LINK_LENGTH) });
export type BffLinkRequest = z.infer<typeof BffLinkRequestSchema>;

/** Códigos de erro próprios de links; as mensagens vêm fixas do backend. */
export const IntegrationErrorCode = {
  linkRejected: "LINK_REJECTED",
  notConfigured: "INTEGRATION_NOT_CONFIGURED",
  providerUnavailable: "PROVIDER_UNAVAILABLE",
  tooManyRuns: "TOO_MANY_RUNS",
} as const;

const SAFE_HOSTS = ["docs.google.com", "drive.google.com", "notion.so", "www.notion.so"];

/** Só abre em nova aba links https de Drive/Notion: nunca `javascript:` vindo de dado externo. */
export function isSafeExternalUrl(value: string | null): value is string {
  if (!value) return false;
  try {
    const url = new URL(value);
    return (
      url.protocol === "https:" &&
      (SAFE_HOSTS.includes(url.hostname) || url.hostname.endsWith(".notion.site") || url.hostname.endsWith(".notion.so"))
    );
  } catch {
    return false;
  }
}

export const LINK_KIND_LABEL: Record<LinkKind, string> = {
  github_repo: "Repositório GitHub",
  drive_folder: "Pasta do Google Drive",
  notion_page: "Página do Notion",
};
