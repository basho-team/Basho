"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { Badge, Card, Empty, ErrorBox, Loading, Mono, buttonClass, inputClass } from "@/components/basho/ui";
import { api } from "@/lib/api";
import { EVIDENCE_KIND, short } from "@/lib/labels";
import type { DemoContext, EvidenceEvent } from "@/lib/types";

export const REPORT_EVIDENCE_KINDS = new Set([
  "activity_record", "technical_justification", "formal_hours_declared", "user_correction",
  "commit_observed", "pull_request_observed", "issue_observed",
]);

export function useEvidence(ctx: DemoContext) {
  return useQuery({
    queryKey: ["evidence", ctx.project_id],
    queryFn: () => api.get<EvidenceEvent[]>(`projects/${ctx.project_id}/evidence`),
    // O ledger também registra cada versão de relatório (payload.artifact): não é evidência citável.
    select: (events) =>
      events.filter((e) => REPORT_EVIDENCE_KINDS.has(e.kind) && !("artifact" in e.payload)),
  });
}

export function evidenceTitle(e: EvidenceEvent): string {
  const title = typeof e.payload.title === "string" ? e.payload.title : e.source_ref ?? e.kind;
  return title;
}

export function EvidenceLabel({ e }: { e: EvidenceEvent }) {
  return (
    <span className="inline-flex flex-wrap items-center gap-1">
      <Badge tone={e.source === "github" ? "info" : e.source === "formal_system" ? "ok" : "neutral"}>
        {EVIDENCE_KIND[e.kind] ?? e.kind}
      </Badge>
      <span>{evidenceTitle(e)}</span>
      <Mono>{short(e.id)}</Mono>
    </span>
  );
}

function belongsTo(e: EvidenceEvent, userId: string): boolean {
  return e.actor.id === userId || e.payload.researcher_id === userId;
}

export function EvidencePanel({ ctx, userId }: { ctx: DemoContext; userId: string }) {
  const evidence = useEvidence(ctx);
  const queryClient = useQueryClient();
  const [kind, setKind] = useState("activity_record");
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [hours, setHours] = useState("");
  const register = useMutation({
    mutationFn: () => api.post<EvidenceEvent>(`projects/${ctx.project_id}/evidence`, {
      kind, title, description,
      hours: kind === "formal_hours_declared" ? Number(hours) : undefined,
    }),
    onSuccess: () => {
      setTitle(""); setDescription(""); setHours("");
      void queryClient.invalidateQueries({ queryKey: ["evidence"] });
    },
  });
  const mine = (evidence.data ?? []).filter((e) => belongsTo(e, userId));
  const others = (evidence.data ?? []).filter((e) => !belongsTo(e, userId));
  return (
    <Card title="Evidências do projeto (ledger append-only)">
      <form
        className="mb-4 grid gap-2 rounded border border-zinc-200 bg-zinc-50 p-3 sm:grid-cols-2"
        onSubmit={(e) => { e.preventDefault(); register.mutate(); }}
      >
        <label className="text-sm">Tipo
          <select className={inputClass} value={kind} onChange={(e) => setKind(e.target.value)}>
            <option value="activity_record">Registro de atividade</option>
            <option value="technical_justification">Justificativa técnica / resultado</option>
          </select>
        </label>
        <label className="text-sm">Título
          <input className={inputClass} value={title} onChange={(e) => setTitle(e.target.value)} minLength={3} required />
        </label>
        <label className="text-sm sm:col-span-2">Descrição
          <textarea className={inputClass} rows={2} value={description} onChange={(e) => setDescription(e.target.value)} minLength={10} required />
        </label>
        <p className="text-xs text-zinc-500 sm:col-span-2">Horas não são registradas aqui: vêm do registro formal da coordenação/RH.</p>
        {kind === "formal_hours_declared" && (
          <label className="text-sm">Horas declaradas
            <input className={inputClass} type="number" min={1} max={744} value={hours} onChange={(e) => setHours(e.target.value)} required />
            <span className="text-xs text-zinc-500">Só aqui entram horas — nunca no texto do relatório.</span>
          </label>
        )}
        <div className="flex items-end sm:col-span-2">
          <button className={buttonClass} disabled={register.isPending}>
            {register.isPending ? "Registrando…" : "Registrar evidência"}
          </button>
        </div>
        {register.isError && <div className="sm:col-span-2"><ErrorBox error={register.error} /></div>}
      </form>
      {evidence.isPending && <Loading />}
      {evidence.isError && <ErrorBox error={evidence.error} onRetry={() => void evidence.refetch()} />}
      {evidence.data && (
        <div className="grid gap-3 md:grid-cols-2">
          <div>
            <h3 className="mb-1 text-sm font-medium">Suas evidências</h3>
            {mine.length === 0 ? <Empty>Nenhuma evidência sua ainda.</Empty> : (
              <ul className="space-y-1 text-sm">{mine.map((e) => <li key={e.id}><EvidenceLabel e={e} /></li>)}</ul>
            )}
          </div>
          <div>
            <h3 className="mb-1 text-sm font-medium">Outras evidências do projeto</h3>
            {others.length === 0 ? <Empty>Nenhuma.</Empty> : (
              <ul className="space-y-1 text-sm">{others.map((e) => <li key={e.id}><EvidenceLabel e={e} /></li>)}</ul>
            )}
          </div>
        </div>
      )}
    </Card>
  );
}
