"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { EvidencePicker } from "@/components/basho/researcher/evidence-picker";
import { useEvidence } from "@/components/basho/researcher/evidence-panel";
import { Card, ErrorBox, buttonClass, inputClass, secondaryButtonClass } from "@/components/basho/ui";
import { api } from "@/lib/api";
import { OUTCOME, SECTION } from "@/lib/labels";
import type { ClaimSection, ClaimStatus, DemoContext, Draft, Outcome, ReportVersionOut } from "@/lib/types";

interface ClaimRow { section: ClaimSection; text: string; status: ClaimStatus; evidence: string[]; question: string; reason: string }
interface ExpRow { description: string; outcome: Outcome; evidence: string[] }
interface GapRow { field: string; question: string; ask_role: string }

const NEW_CLAIM: ClaimRow = { section: "method", text: "", status: "supported", evidence: [], question: "", reason: "" };

export function buildDraft(ctx: DemoContext, researcherId: string, summary: string, claims: ClaimRow[],
  experiments: ExpRow[], gaps: GapRow[], hours: string[]): Draft {
  return {
    project_id: ctx.project_id,
    researcher_id: researcherId,
    period: ctx.period,
    summary,
    claims: claims.map((c) => ({
      section: c.section, text: c.text, status: c.status,
      evidence_ids: c.status === "pending" && c.evidence.length === 0 ? [] : c.evidence,
      ...(c.status === "pending" ? { question: c.question, ask_role: "pesquisador" } : {}),
      ...(c.status === "disputed" ? { dispute_reason: c.reason } : {}),
    })),
    experiments: experiments.map((x) => ({ description: x.description, outcome: x.outcome, evidence_ids: x.evidence })),
    missing: gaps,
    formal_hours_event_ids: hours,
  };
}

export function ReportBuilder({ ctx, researcherId }: { ctx: DemoContext; researcherId: string }) {
  const evidence = useEvidence(ctx);
  const queryClient = useQueryClient();
  const [summary, setSummary] = useState("");
  const [claims, setClaims] = useState<ClaimRow[]>([{ ...NEW_CLAIM }]);
  const [experiments, setExperiments] = useState<ExpRow[]>([]);
  const [hours, setHours] = useState<string[]>([]);
  const [gaps, setGaps] = useState<GapRow[]>([]);
  const all = evidence.data ?? [];
  const hoursEvents = all.filter((e) => e.kind === "formal_hours_declared");
  const nonHours = all.filter((e) => e.kind !== "formal_hours_declared");

  const create = useMutation({
    mutationFn: () => {
      const effectiveGaps = hours.length === 0 && !gaps.some((g) => g.field === "formal_hours")
        ? [...gaps, { field: "formal_hours", ask_role: "coordenador", question: "Quais horas o registro formal informa para o período?" }]
        : gaps;
      return api.post<ReportVersionOut>("reports", buildDraft(ctx, researcherId, summary, claims, experiments, effectiveGaps, hours));
    },
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ["reports"] }),
  });

  const setClaim = (i: number, patch: Partial<ClaimRow>) => setClaims(claims.map((c, j) => (j === i ? { ...c, ...patch } : c)));
  const setExp = (i: number, patch: Partial<ExpRow>) => setExperiments(experiments.map((x, j) => (j === i ? { ...x, ...patch } : x)));

  return (
    <Card title="Construir relatório do período">
      <div className="mb-4 rounded border border-amber-200 bg-amber-50 p-3 text-sm">
        <button type="button" className={secondaryButtonClass} disabled title={ctx.ai_detail}>
          Gerar rascunho com IA (indisponível nesta demo)
        </button>
        <p className="mt-2 text-xs text-amber-900">{ctx.ai_detail}</p>
      </div>
      <form className="space-y-4" onSubmit={(e) => { e.preventDefault(); create.mutate(); }}>
        <label className="block text-sm">Resumo do período
          <textarea className={inputClass} rows={2} minLength={20} required value={summary} onChange={(e) => setSummary(e.target.value)} />
        </label>

        <fieldset className="space-y-3">
          <legend className="text-sm font-medium">Afirmações (cada uma cita evidência, ou vira pendência/conflito)</legend>
          {claims.map((c, i) => (
            <div key={i} className="grid gap-2 rounded border border-zinc-200 p-2 sm:grid-cols-[10rem_9rem_1fr]">
              <select className={inputClass} value={c.section} onChange={(e) => setClaim(i, { section: e.target.value as ClaimSection })}>
                {Object.entries(SECTION).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
              </select>
              <select className={inputClass} value={c.status} onChange={(e) => setClaim(i, { status: e.target.value as ClaimStatus })}>
                <option value="supported">Com evidência</option>
                <option value="pending">Pendente (pergunta)</option>
                <option value="disputed">Em conflito</option>
              </select>
              <input className={inputClass} placeholder="Texto da afirmação" minLength={10} required value={c.text} onChange={(e) => setClaim(i, { text: e.target.value })} />
              {c.status === "pending" && (
                <input className={`${inputClass} sm:col-span-3`} placeholder="Pergunta objetiva ao responsável" minLength={10} required value={c.question} onChange={(e) => setClaim(i, { question: e.target.value })} />
              )}
              {c.status === "disputed" && (
                <input className={`${inputClass} sm:col-span-3`} placeholder="Motivo do conflito entre evidências" minLength={10} required value={c.reason} onChange={(e) => setClaim(i, { reason: e.target.value })} />
              )}
              <div className="sm:col-span-3">
                <EvidencePicker evidence={nonHours} value={c.evidence} onChange={(ids) => setClaim(i, { evidence: ids })} />
              </div>
              {claims.length > 1 && (
                <button type="button" className="text-left text-xs text-rose-700 underline sm:col-span-3" onClick={() => setClaims(claims.filter((_, j) => j !== i))}>remover afirmação</button>
              )}
            </div>
          ))}
          <button type="button" className={secondaryButtonClass} onClick={() => setClaims([...claims, { ...NEW_CLAIM }])}>+ afirmação</button>
        </fieldset>

        <fieldset className="space-y-3">
          <legend className="text-sm font-medium">Experimentos (negativos e inconclusivos também são resultado)</legend>
          {experiments.map((x, i) => (
            <div key={i} className="grid gap-2 rounded border border-zinc-200 p-2 sm:grid-cols-[1fr_10rem]">
              <input className={inputClass} placeholder="Descrição do experimento" minLength={10} required value={x.description} onChange={(e) => setExp(i, { description: e.target.value })} />
              <select className={inputClass} value={x.outcome} onChange={(e) => setExp(i, { outcome: e.target.value as Outcome })}>
                {Object.entries(OUTCOME).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
              </select>
              <div className="sm:col-span-2"><EvidencePicker evidence={nonHours} value={x.evidence} onChange={(ids) => setExp(i, { evidence: ids })} /></div>
              <button type="button" className="text-left text-xs text-rose-700 underline" onClick={() => setExperiments(experiments.filter((_, j) => j !== i))}>remover experimento</button>
            </div>
          ))}
          <button type="button" className={secondaryButtonClass} onClick={() => setExperiments([...experiments, { description: "", outcome: "positive", evidence: [] }])}>+ experimento</button>
        </fieldset>

        <fieldset className="space-y-2">
          <legend className="text-sm font-medium">Horas: só por referência a registro formal</legend>
          <EvidencePicker evidence={hoursEvents} value={hours} onChange={setHours} />
          {hours.length === 0 && <p className="text-xs text-amber-800">Sem registro formal: o relatório abrirá a lacuna “formal_hours” automaticamente.</p>}
        </fieldset>

        <fieldset className="space-y-2">
          <legend className="text-sm font-medium">Outras lacunas</legend>
          {gaps.map((g, i) => (
            <div key={i} className="grid gap-2 sm:grid-cols-[10rem_1fr]">
              <input className={inputClass} placeholder="campo" required value={g.field} onChange={(e) => setGaps(gaps.map((x, j) => (j === i ? { ...x, field: e.target.value } : x)))} />
              <input className={inputClass} placeholder="pergunta objetiva" minLength={10} required value={g.question} onChange={(e) => setGaps(gaps.map((x, j) => (j === i ? { ...x, question: e.target.value } : x)))} />
            </div>
          ))}
          <button type="button" className={secondaryButtonClass} onClick={() => setGaps([...gaps, { field: "", question: "", ask_role: "pesquisador" }])}>+ lacuna</button>
        </fieldset>

        <button className={buttonClass} disabled={create.isPending || evidence.isPending}>
          {create.isPending ? "Criando…" : "Criar relatório (versão 1)"}
        </button>
        {create.isError && <ErrorBox error={create.error} />}
      </form>
    </Card>
  );
}
