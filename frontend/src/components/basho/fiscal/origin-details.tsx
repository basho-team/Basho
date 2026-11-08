"use client";

import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { ErrorBox, Loading } from "@/components/basho/ui";
import { api } from "@/lib/api";
import type { DossierItem, EvidenceEvent, FiscalSource, ReportVersionOut } from "@/lib/types";

export function OriginDetails({ item, source }: { item: DossierItem; source: FiscalSource }) {
  const [open, setOpen] = useState(false);
  const version = useQuery({
    queryKey: ["origin-version", item.version_id],
    queryFn: () => api.get<ReportVersionOut>(`reports/${item.version_id}`), enabled: open,
  });
  const events = useQuery({
    queryKey: ["origin-evidence", source.project_id],
    queryFn: () => api.get<EvidenceEvent[]>(`projects/${source.project_id}/evidence`), enabled: open,
  });
  const event = events.data?.find((e) => source.reference === `evidence:${e.id}`);
  const ids = version.data?.version[`${item.item_kind}_ids`];
  const itemFound = ids?.includes(item.item_id);
  return (
    <details className="mt-1 max-w-sm break-all" onToggle={(e) => setOpen(e.currentTarget.open)}>
      <summary className="cursor-pointer underline">Ver origem completa</summary>
      <OriginMetadata item={item} source={source} />
      {open && (
        <div className="mt-2 space-y-2">
          {(events.isPending || version.isPending) && <Loading />}
          {version.isError && <ErrorBox error={version.error} onRetry={() => void version.refetch()} />}
          {events.isError && <ErrorBox error={events.error} onRetry={() => void events.refetch()} />}
          {version.data && <p>Versão v{version.data.version.number}: {itemFound ? "item localizado na versão exata" : "item não localizado nesta versão"}.</p>}
          {events.data && !event && <p className="text-amber-800">Conteúdo não localizado entre os 200 eventos mais recentes. Isso não prova ausência da evidência.</p>}
          {event && (
            <>
              <p>Tipo: {event.kind} · origem: {event.source} · registrado em: {event.created_at}</p>
              {event.content_hash !== source.revision && <p role="alert">O hash retornado difere da revisão citada. Revisão humana necessária.</p>}
              <p>Referência externa: {event.source_ref ?? "Não informada"}</p>
              <pre className="max-h-64 overflow-auto whitespace-pre-wrap rounded bg-zinc-50 p-2">{JSON.stringify(event.payload, null, 2)}</pre>
              <p className="text-zinc-500">Hash exibido conforme o ledger; não é validação de conteúdo ou elegibilidade fiscal.</p>
            </>
          )}
        </div>
      )}
    </details>
  );
}

function OriginMetadata({ item, source }: { item: DossierItem; source: FiscalSource }) {
  return (
      <dl className="mt-2 space-y-1 text-xs">
        <dt>Pesquisador</dt><dd>{item.researcher_id}</dd>
        <dt>Tenant</dt><dd>{source.tenant_id}</dd>
        <dt>Projeto</dt><dd>{source.project_id}</dd>
        <dt>Versão</dt><dd>{item.version_id}</dd>
        <dt>Item ({item.item_kind})</dt><dd>{item.item_id}</dd>
        <dt>Revisão humana do texto</dt><dd>{item.researcher_review_id ?? "Ausente"}</dd>
        <dt>Referência da evidência</dt><dd>{source.reference}</dd>
        <dt>Hash registrado da evidência</dt><dd>{source.revision}</dd>
        <dt>Localizador</dt><dd>{source.locator}</dd>
      </dl>
  );
}
