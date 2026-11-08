/**
 * Cliente das rotas BFF de links e publicações (ADR-0010). O navegador declara só o papel da
 * demonstração (`X-Demo-Role`); identidade e segredo ficam no servidor do Next.
 */
import type { z } from "zod";
import { BffErrorCode, DEMO_ROLE_HEADER } from "@/lib/bff/contract";
import {
  AgentRunSchema,
  integrationPaths,
  IntegrationsConfigSchema,
  LinkSchema,
  LinksSchema,
  SourcesSchema,
  PublicationsSchema,
} from "@/lib/bff/integrations-contract";
import { ApiErrorSchema } from "@/lib/contracts/provisional";
import { DataSourceError } from "@/lib/data/source";
import { currentDemoRole } from "@/lib/demo/role";

const UNEXPECTED = "Resposta inesperada do servidor.";

function clientError(code: string, message: string, retryable = false): DataSourceError {
  return new DataSourceError({ code, message, correlation_id: `ui-${Date.now()}`, retryable });
}

export function createIntegrationsApi(doFetch: typeof fetch = (input, init) => fetch(input, init)) {
  async function request<S extends z.ZodType>(url: string, init: RequestInit, schema: S): Promise<z.output<S>> {
    const role = currentDemoRole();
    const headers = { Accept: "application/json", ...(role ? { [DEMO_ROLE_HEADER]: role } : {}), ...init.headers };
    let res: Response;
    try {
      res = await doFetch(url, { ...init, cache: "no-store", headers });
    } catch {
      throw clientError(BffErrorCode.backendUnavailable, "Sem conexão com o servidor. Tente de novo.", true);
    }
    const body: unknown = await res.json().catch(() => null);
    if (!res.ok) {
      const error = ApiErrorSchema.safeParse(body);
      throw error.success ? new DataSourceError(error.data) : clientError(BffErrorCode.invalidResponse, UNEXPECTED, true);
    }
    const parsed = schema.safeParse(body);
    if (!parsed.success) throw clientError(BffErrorCode.invalidResponse, UNEXPECTED);
    return parsed.data;
  }

  const json = (method: string, body?: unknown): RequestInit => ({
    method,
    ...(body === undefined ? {} : { headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }),
  });

  return {
    config: () => request(integrationPaths.config(), json("GET"), IntegrationsConfigSchema),
    links: (projectId: string) => request(integrationPaths.links(projectId), json("GET"), LinksSchema),
    sources: (projectId: string) => request(integrationPaths.sources(projectId), json("GET"), SourcesSchema),
    addLink: (projectId: string, url: string) =>
      request(integrationPaths.links(projectId), json("POST", { url }), LinkSchema),
    revokeLink: (projectId: string, linkId: string) =>
      request(integrationPaths.link(projectId, linkId), json("DELETE"), LinkSchema),
    publications: (projectId: string) => request(integrationPaths.publications(projectId), json("GET"), PublicationsSchema),
    generate: (projectId: string) => request(integrationPaths.generate(projectId), json("POST"), AgentRunSchema),
    run: (runId: string) => request(integrationPaths.run(runId), json("GET"), AgentRunSchema),
    publish: (projectId: string) => request(integrationPaths.publications(projectId), json("POST"), PublicationsSchema),
  };
}

export const integrationsApi = createIntegrationsApi();
