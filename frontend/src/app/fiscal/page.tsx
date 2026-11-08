"use client";

import { useQuery } from "@tanstack/react-query";

import { periodQuery, personName } from "@/components/basho/hooks";
import { OriginDetails } from "@/components/basho/fiscal/origin-details";
import { RequirePersona, Shell } from "@/components/basho/shell";
import { Badge, Card, Empty, ErrorBox, Loading, Mono } from "@/components/basho/ui";
import { ApiError, api } from "@/lib/api";
import { DOSSIER_STATUS, GAP, short } from "@/lib/labels";
import type { DemoContext, Dossier } from "@/lib/types";

const TONE: Record<string, "ok" | "warn" | "bad" | "info" | "neutral"> = {
  supported: "ok", pending: "warn", disputed: "bad", gap: "warn",
  result_positive: "ok", result_negative: "bad", result_inconclusive: "warn",
};

function FiscalWork({ ctx }: { ctx: DemoContext }) {
  const dossier = useQuery({
    queryKey: ["dossier", ctx.project_id],
    queryFn: () => api.get<Dossier>(`projects/${ctx.project_id}/dossier?${periodQuery(ctx)}&fiscal_year=${ctx.fiscal_year}`),
    retry: (count, error) => !(error instanceof ApiError && error.status === 404) && count < 2,
  });
  if (dossier.isPending) return <Loading />;
  if (dossier.isError) {
    if (dossier.error instanceof ApiError && dossier.error.status === 404) return <Empty>Nenhum relatório no período para montar o dossiê.</Empty>;
    return <ErrorBox error={dossier.error} onRetry={() => void dossier.refetch()} />;
  }
  const d = dossier.data;
  return (
    <div className="space-y-6">
      <Card title={`Dossiê do período ${d.period_start} a ${d.period_end} · ano-base ${ctx.fiscal_year}`}>
        <p className="mb-2 text-sm text-zinc-700">{d.note}</p>
        {d.period_gaps.length > 0 && <p className="text-sm text-amber-800">{d.period_gaps.map((g) => GAP[g] ?? g).join("; ")}</p>}
        <ul className="grid gap-3 sm:grid-cols-2">
          {d.researchers.map((r) => (
            <li key={r.researcher_id} className="rounded border border-zinc-200 p-3 text-sm">
              <p><strong>{personName(ctx, r.researcher_id)}</strong> — v{r.version_number} <Mono>{short(r.version_id)}</Mono></p>
              <p>Confirmação do texto pelo pesquisador: {r.researcher_review_id ? <><Badge tone="ok">revisão {short(r.researcher_review_id)}</Badge></> : <Badge tone="warn">ausente</Badge>}</p>
              <p>Horas: {r.formal_hours.length ? r.formal_hours.map((h) => <Mono key={h.reference}>{h.reference.replace("evidence:", "").slice(0, 8)} ({h.origin})</Mono>) : <Badge tone="warn">sem registro formal</Badge>}</p>
              {r.gaps.length > 0 && <p className="text-xs text-amber-800">{r.gaps.map((g) => GAP[g] ?? g).join("; ")}</p>}
            </li>
          ))}
        </ul>
      </Card>
      <Card title="Itens e evidências (origem verificável)">
        {d.items.length === 0 && <Empty>Nenhum item.</Empty>}
        <div className="overflow-x-auto">
          <table className="w-full min-w-[40rem] text-left text-sm">
            <thead className="text-xs text-zinc-500"><tr><th className="p-2">Situação</th><th className="p-2">Item</th><th className="p-2">Evidências (hash · localizador)</th><th className="p-2">Lacunas</th></tr></thead>
            <tbody>
              {d.items.map((i) => (
                <tr key={`${i.version_id}-${i.item_id}`} className="border-t border-zinc-100 align-top">
                  <td className="p-2"><Badge tone={TONE[i.status] ?? "neutral"}>{DOSSIER_STATUS[i.status] ?? i.status}</Badge></td>
                  <td className="p-2">{i.text}<div className="text-xs text-zinc-500">{personName(ctx, i.researcher_id)} · {i.item_kind} <Mono>{short(i.item_id)}</Mono> · versão <Mono>{short(i.version_id)}</Mono></div></td>
                  <td className="p-2 text-xs">
                    {i.sources.length === 0 ? <Badge tone="warn">nenhuma evidência válida</Badge> : (
                      <ul className="space-y-1">{i.sources.map((s) => <li key={s.reference}><Mono>{s.reference.replace("evidence:", "").slice(0, 8)}</Mono> {s.origin} · <Mono>{s.revision.slice(0, 10)}</Mono><div className="break-all text-zinc-400">{s.locator}</div><OriginDetails item={i} source={s} /></li>)}</ul>
                    )}
                  </td>
                  <td className="p-2 text-xs text-amber-800">{i.gaps.map((g) => GAP[g] ?? g).join("; ") || "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  );
}

export default function FiscalPage() {
  return (
    <Shell>
      {(ctx, persona) => (
        <>
          <h1 className="mb-4 text-2xl font-semibold">Fiscal</h1>
          <RequirePersona persona={persona} role="fiscal" ctx={ctx}><FiscalWork ctx={ctx} /></RequirePersona>
        </>
      )}
    </Shell>
  );
}
