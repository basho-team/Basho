"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { periodQuery, personName } from "@/components/basho/hooks";
import { useReports } from "@/components/basho/reports-query";
import { RequirePersona, Shell } from "@/components/basho/shell";
import { Badge, Card, Empty, ErrorBox, Loading, Mono, buttonClass, inputClass, secondaryButtonClass } from "@/components/basho/ui";
import { api } from "@/lib/api";
import { OUTCOME, REVIEW_STATE, SECTION, short } from "@/lib/labels";
import type { ConsolidationOut, DemoContext, ReportVersionOut, SourceRef } from "@/lib/types";

function Origin({ s, ctx }: { s: SourceRef; ctx: DemoContext }) {
  return (
    <span className="text-xs text-zinc-500">
      — {personName(ctx, s.researcher_id)}, v{s.version_number}, item <Mono>{short(s.item_id)}</Mono>
      {s.researcher_review_id ? <Badge tone="ok">texto confirmado</Badge> : <Badge tone="warn">rascunho não confirmado</Badge>}
    </span>
  );
}

function ManagerReview({ report }: { report: ReportVersionOut }) {
  const queryClient = useQueryClient();
  const [comment, setComment] = useState("");
  const review = useMutation({
    mutationFn: (decision: "text_approved" | "changes_requested") =>
      api.post(`reports/${report.current_version_id}/review`, { decision, comment: comment || undefined }),
    onSuccess: () => { setComment(""); void queryClient.invalidateQueries(); },
  });
  return (
    <div className="mt-2 flex flex-wrap items-center gap-2">
      <input className={`${inputClass} max-w-xs`} placeholder="Comentário (opcional)" value={comment} onChange={(e) => setComment(e.target.value)} />
      <button type="button" className={buttonClass} disabled={review.isPending} onClick={() => review.mutate("text_approved")}>Aceitar v{report.status.current_version_number}</button>
      <button type="button" className={secondaryButtonClass} disabled={review.isPending} onClick={() => review.mutate("changes_requested")}>Pedir esclarecimento</button>
      {review.isError && <ErrorBox error={review.error} />}
    </div>
  );
}

function FormalHoursForm({ ctx }: { ctx: DemoContext }) {
  const queryClient = useQueryClient();
  const researchers = ctx.people.filter((p) => p.role === "researcher");
  const [researcherId, setResearcherId] = useState(researchers[0]?.id ?? "");
  const [hours, setHours] = useState("");
  const [description, setDescription] = useState("");
  const declare = useMutation({
    mutationFn: () => api.post(`projects/${ctx.project_id}/evidence`, {
      kind: "formal_hours_declared",
      title: `Horas formais — ${personName(ctx, researcherId)} — ${ctx.period.start.slice(0, 7)}`,
      description, hours: Number(hours), researcher_id: researcherId,
    }),
    onSuccess: () => { setHours(""); setDescription(""); void queryClient.invalidateQueries({ queryKey: ["evidence"] }); },
  });
  return (
    <Card title="Registrar horas formais (coordenação)">
      <form className="grid gap-2 sm:grid-cols-[1fr_8rem_2fr_auto]" onSubmit={(e) => { e.preventDefault(); declare.mutate(); }}>
        <select className={inputClass} value={researcherId} onChange={(e) => setResearcherId(e.target.value)}>
          {researchers.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
        </select>
        <input className={inputClass} type="number" min={1} max={744} placeholder="horas" required value={hours} onChange={(e) => setHours(e.target.value)} />
        <input className={inputClass} placeholder="Base do registro (ex.: folha de ponto conferida)" minLength={10} required value={description} onChange={(e) => setDescription(e.target.value)} />
        <button className={buttonClass} disabled={declare.isPending}>Registrar</button>
      </form>
      <p className="mt-2 text-xs text-zinc-500">Horas entram no ledger como registro formal da coordenação; o pesquisador só as referencia.</p>
      {declare.isError && <ErrorBox error={declare.error} />}
      {declare.isSuccess && <p className="mt-1 text-xs text-emerald-700">Registro gravado no ledger.</p>}
    </Card>
  );
}

function ManagerWork({ ctx }: { ctx: DemoContext }) {
  const reports = useReports(ctx);
  const cons = useQuery({
    queryKey: ["consolidation", ctx.project_id],
    queryFn: () => api.get<ConsolidationOut>(`projects/${ctx.project_id}/consolidation?${periodQuery(ctx)}`),
  });
  const [showMd, setShowMd] = useState(false);
  const c = cons.data?.consolidation;
  return (
    <div className="space-y-6">
      <Card title="Relatórios do período">
        {reports.isPending && <Loading />}
        {reports.isError && <ErrorBox error={reports.error} onRetry={() => void reports.refetch()} />}
        {reports.data?.length === 0 && <Empty>Nenhum relatório no período ainda.</Empty>}
        <ul className="space-y-3">
          {reports.data?.map((r) => (
            <li key={r.current_version_id} className="rounded border border-zinc-200 p-3 text-sm">
              <div className="flex flex-wrap items-center gap-2">
                <strong>{personName(ctx, r.status.researcher_id)}</strong>
                <span>v{r.status.current_version_number}</span>
                <Badge tone={r.status.researcher.state === "text_approved" ? "ok" : "warn"}>Pesquisador: {REVIEW_STATE[r.status.researcher.state]}</Badge>
                <Badge tone={r.status.manager.state === "text_approved" ? "ok" : "neutral"}>Gerente: {REVIEW_STATE[r.status.manager.state]}</Badge>
                {r.status.approval_outdated && <Badge tone="warn">confirmação desatualizada</Badge>}
              </div>
              <ManagerReview report={r} />
            </li>
          ))}
        </ul>
      </Card>
      <FormalHoursForm ctx={ctx} />
      <Card title="Consolidação gerencial" actions={c && <button type="button" className={secondaryButtonClass} onClick={() => setShowMd(!showMd)}>{showMd ? "Ver estruturado" : "Ver texto exportável"}</button>}>
        {cons.isPending && <Loading />}
        {cons.isError && <ErrorBox error={cons.error} onRetry={() => void cons.refetch()} />}
        {cons.data && !c && <Empty>Sem relatórios para consolidar.</Empty>}
        {c && showMd && <pre className="max-h-[32rem] overflow-auto whitespace-pre-wrap rounded bg-zinc-50 p-3 text-xs">{cons.data?.summary_markdown}</pre>}
        {c && !showMd && (
          <div className="space-y-4 text-sm">
            <p>Consolidação <Mono>{short(c.consolidation_id)}</Mono> · {c.reports.length} relatório(s) · {c.all_text_approved ? <Badge tone="ok">todos os textos confirmados</Badge> : <Badge tone="warn">há textos não confirmados</Badge>}</p>
            <div className="flex flex-wrap gap-2">
              <Badge tone="ok">Positivos: {c.outcome_counts.positive}</Badge>
              <Badge tone="bad">Negativos: {c.outcome_counts.negative}</Badge>
              <Badge tone="warn">Inconclusivos: {c.outcome_counts.inconclusive}</Badge>
            </div>
            <section><h3 className="font-medium">Resultados de experimentos</h3>
              <ul className="list-disc pl-5">{c.results.map((r) => <li key={r.source.item_id}><strong>{OUTCOME[r.outcome ?? ""]}:</strong> {r.description} <Origin s={r.source} ctx={ctx} /></li>)}</ul>
            </section>
            <section><h3 className="font-medium">Avanços</h3>
              {c.advances.length === 0 ? <Empty>Nenhum.</Empty> : <ul className="list-disc pl-5">{c.advances.map((a) => <li key={a.source.item_id}>[{SECTION[a.section ?? ""]}] {a.text} <Origin s={a.source} ctx={ctx} /></li>)}</ul>}
            </section>
            <section><h3 className="font-medium">Pendências e perguntas abertas</h3>
              {c.open_questions.length === 0 ? <Empty>Nenhuma.</Empty> : <ul className="list-disc pl-5">{c.open_questions.map((q) => <li key={q.source.item_id}><strong>{q.ask_role}</strong> ({q.topic}): {q.question} <Origin s={q.source} ctx={ctx} /></li>)}</ul>}
            </section>
            <section><h3 className="font-medium">Conflitos entre evidências</h3>
              {c.disputes.length === 0 ? <Empty>Nenhum.</Empty> : <ul className="list-disc pl-5">{c.disputes.map((d) => <li key={d.source.item_id}>{d.text} <em>Motivo: {d.reason}</em> <Origin s={d.source} ctx={ctx} /></li>)}</ul>}
            </section>
            <p className="text-xs text-zinc-500">{c.note}</p>
          </div>
        )}
      </Card>
    </div>
  );
}

export default function ManagerPage() {
  return (
    <Shell>
      {(ctx, persona) => (
        <>
          <h1 className="mb-4 text-2xl font-semibold">Gerente</h1>
          <RequirePersona persona={persona} role="manager" ctx={ctx}><ManagerWork ctx={ctx} /></RequirePersona>
        </>
      )}
    </Shell>
  );
}
