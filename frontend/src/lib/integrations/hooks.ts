"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { integrationsApi } from "@/lib/integrations/client";

const PUBLICATION_POLL_MS = 3000;

export const integrationKeys = {
  config: ["basho", "integrations", "config"] as const,
  links: (projectId: string) => ["basho", "integrations", "links", projectId] as const,
  publications: (projectId: string) => ["basho", "integrations", "publications", projectId] as const,
  sources: (projectId: string) => ["basho", "integrations", "sources", projectId] as const,
};

/** Fontes da organização no ledger do projeto; atualiza a cada 30 s (o worker sincroniza por run). */
export function useOrgSources(projectId: string | undefined) {
  return useQuery({
    queryKey: integrationKeys.sources(projectId ?? ""),
    queryFn: () => integrationsApi.sources(projectId ?? ""),
    enabled: Boolean(projectId),
    refetchInterval: 30_000,
  });
}

export function useIntegrationsConfig() {
  return useQuery({ queryKey: integrationKeys.config, queryFn: () => integrationsApi.config(), staleTime: 60_000 });
}

export function useLinks(projectId: string) {
  return useQuery({ queryKey: integrationKeys.links(projectId), queryFn: () => integrationsApi.links(projectId) });
}

export function useAddLink(projectId: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (url: string) => integrationsApi.addLink(projectId, url),
    onSuccess: () => client.invalidateQueries({ queryKey: integrationKeys.links(projectId) }),
  });
}

export function useRevokeLink(projectId: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (linkId: string) => integrationsApi.revokeLink(projectId, linkId),
    onSuccess: () => client.invalidateQueries({ queryKey: integrationKeys.links(projectId) }),
  });
}

/** Atualiza sozinha enquanto houver publicação na fila ou em andamento. */
export function usePublications(projectId: string) {
  return useQuery({
    queryKey: integrationKeys.publications(projectId),
    queryFn: () => integrationsApi.publications(projectId),
    refetchInterval: (query) =>
      query.state.data?.items.some((item) => item.status === "queued" || item.status === "running")
        ? PUBLICATION_POLL_MS
        : false,
  });
}

/** Pede ao agente o relatório do período; o estado do run é acompanhado por `useRun`. */
export function useGenerate(projectId: string) {
  return useMutation({ mutationFn: () => integrationsApi.generate(projectId) });
}

export function useRun(runId: string | undefined, projectId: string) {
  const client = useQueryClient();
  return useQuery({
    queryKey: ["basho", "integrations", "run", runId] as const,
    enabled: runId !== undefined,
    queryFn: async () => {
      const run = await integrationsApi.run(runId as string);
      // Run concluído: a publicação acontece sozinha no worker; atualiza a lista logo em seguida.
      if (run.status === "completed" || run.status === "failed") {
        void client.invalidateQueries({ queryKey: integrationKeys.publications(projectId) });
      }
      return run;
    },
    refetchInterval: (query) =>
      query.state.data && (query.state.data.status === "queued" || query.state.data.status === "running")
        ? PUBLICATION_POLL_MS
        : false,
  });
}

export function usePublishNow(projectId: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: () => integrationsApi.publish(projectId),
    onSuccess: (data) => client.setQueryData(integrationKeys.publications(projectId), data),
  });
}
