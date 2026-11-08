"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { EvidencePicker } from "@/components/basho/researcher/evidence-picker";
import { EvidenceLabel, useEvidence } from "@/components/basho/researcher/evidence-panel";
import { Badge, Card, ErrorBox, Loading, Mono, buttonClass, inputClass, secondaryButtonClass } from "@/components/basho/ui";
import { ApiError, api } from "@/lib/api";
import { CLAIM_STATUS, OUTCOME, REVIEW_STATE, SECTION, short } from "@/lib/labels";
import type { ChecksOut, ClaimStatus, DemoContext, EvidenceEvent, Outcome, ReportVersionOut, VersionConflict } from "@/lib/types";

function Refs({ ids, evidence }: { ids: string[]; evidence: EvidenceEvent[] }) {
  if (ids.length === 0) return <span className="text-xs text-zinc-500">sem evidência citada</span>;
  return (
    <ul className="mt-1 space-y-0.5 text-xs">
      {ids.map((id) => {
        const e = evidence.find((x) => x.id === id);
        return <li key={id}>{e ? <EvidenceLabel e={e} /> : <span className="text-rose-700">evidência {short(id)} não encontrada</span>}</li>;
      })}
    </ul>
  );
}

const STATUS_TONE: Record<string, "ok" | "warn" | "bad"> = { supported: "ok", pending: "warn", disputed: "bad" };
const OUTCOME_TONE: Record<string, "ok" | "bad" | "warn"> = { positive: "ok", negative: "bad", inconclusive: "warn" };

function VersionBody({ out, evidence }: { out: ReportVersionOut; evidence: EvidenceEvent[] }) {
  const v = out.version;
  return (
    <div className="space-y-4 text-sm">
      <p className="text-zinc-700">{v.draft.summary}</p>
      <div>
        <h3 className="mb-1 font-medium">Afirmações</h3>
        <ul className="space-y-2">
          {v.draft.claims.map((c, i) => (
            <li key={v.claim_ids[i]} className="rounded border border-zinc-200 p-2">
              <div className="flex flex-wrap items-center gap-1">
                <Badge>{SECTION[c.section]}</Badge>
                <Badge tone={STATUS_TONE[c.status]}>{CLAIM_STATUS[c.status]}</Badge>
                <Mono>item {short(v.claim_ids[i])}</Mono>
              </div>
              <p className="mt-1">{c.text}</p>
              {c.question && <p className="text-xs text-amber-800">Pergunta: {c.question}</p>}
              {c.dispute_reason && <p className="text-xs text-rose-800">Conflito: {c.dispute_reason}</p>}
              <Refs ids={c.evidence_ids} evidence={evidence} />
            </li>
          ))}
        </ul>
      </div>
      <div>
        <h3 className="mb-1 font-medium">Experimentos</h3>
        {v.draft.experiments.length === 0 ? <p className="text-xs text-zinc-500">Nenhum experimento declarado.</p> : (
          <ul className="space-y-2">
            {v.draft.experiments.map((x, i) => (
              <li key={v.experiment_ids[i]} className="rounded border border-zinc-200 p-2">
                <Badge tone={OUTCOME_TONE[x.outcome]}>{OUTCOME[x.outcome]}</Badge> {x.description} <Mono>item {short(v.experiment_ids[i])}</Mono>
                <Refs ids={x.evidence_ids} evidence={evidence} />
              </li>
            ))}
          </ul>
        )}
      </div>
      <div>
        <h3 className="mb-1 font-medium">Lacunas</h3>
        {v.draft.missing.length === 0 ? <p className="text-xs text-emerald-700">Nenhuma lacuna aberta.</p> : (
          <ul className="list-disc pl-5">
            {v.draft.missing.map((m, i) => <li key={v.missing_ids[i]}><strong>{m.field}</strong> ({m.ask_role}): {m.question}</li>)}
          </ul>
        )}
      </div>
      <div>
        <h3 className="mb-1 font-medium">Horas</h3>
        <Refs ids={v.draft.formal_hours_event_ids} evidence={evidence} />
      </div>
      {v.change && (
        <div className="rounded border border-sky-200 bg-sky-50 p-2 text-xs">
          <p className="font-medium">Mudança em relação à v{v.number - 1}: {v.change.reason}</p>
          <ul className="list-disc pl-5">{v.change.operations.map((op, i) => <li key={i}>{op}</li>)}</ul>
        </div>
      )}
      <p className="text-xs text-zinc-500">Hash do conteúdo <Mono>{out.content_hash.slice(0, 16)}</Mono> · evento no ledger <Mono>{short(out.evidence_event_id)}</Mono></p>
    </div>
  );
}

function Checks({ versionId }: { versionId: string }) {
  const run = useMutation({ mutationFn: () => api.post<ChecksOut>(`reports/${versionId}/checks`, {}) });
  return (
    <div className="space-y-2">
      <button type="button" className={secondaryButtonClass} onClick={() => run.mutate()} disabled={run.isPending}>
        {run.isPending ? "Verificando…" : "Rodar verificações"}
      </button>
      {run.isError && <ErrorBox error={run.error} />}
      {run.data && (
        <div className="space-y-1 text-sm">
          <p>Checks determinísticos: <Badge tone={run.data.deterministic.verdict === "pass" ? "ok" : "bad"}>{run.data.deterministic.verdict === "pass" ? "aprovado" : "reprovado"}</Badge></p>
          {run.data.deterministic.issues.length > 0 && (
            <ul className="list-disc pl-5 text-xs">
              {run.data.deterministic.issues.map((i, k) => <li key={k}><Mono>{i.code}</Mono> ({i.severity}): {i.message}</li>)}
            </ul>
          )}
          <p className="text-xs text-amber-800">Checker por IA: {run.data.checker_detail}</p>
        </div>
      )}
    </div>
  );
}

type Op = "revise_claim" | "resolve_missing" | "add_experiment";

function CorrectionForm({ out, ctx, onDone }: { out: ReportVersionOut; ctx: DemoContext; onDone: (newId: string) => void }) {
  const evidence = useEvidence(ctx);
  const v = out.version;
  const [op, setOp] = useState<Op>("revise_claim");
  const first = v.draft.claims[0];
  const [claimId, setClaimId] = useState(v.claim_ids[0] ?? "");
  // Começa com o conteúdo atual da afirmação: corrigir parte do que existe, não do zero.
  const [text, setText] = useState(first?.text ?? "");
  const [status, setStatus] = useState<ClaimStatus>(first?.status ?? "supported");
  const [ids, setIds] = useState<string[]>(first?.evidence_ids ?? []);
  const [missingId, setMissingId] = useState(v.missing_ids[0] ?? "");
  const [outcome, setOutcome] = useState<Outcome>("negative");
  const [reason, setReason] = useState("");
  const all = evidence.data ?? [];
  const gapIndex = v.missing_ids.indexOf(missingId);
  const isHoursGap = gapIndex >= 0 && v.draft.missing[gapIndex]?.field === "formal_hours";

  const operation = () => {
    if (op === "revise_claim") {
      const current = v.draft.claims[v.claim_ids.indexOf(claimId)];
      return {
        kind: op, claim_id: claimId, text, status, evidence_ids: ids,
        ...(status === "pending" ? { question: current?.question ?? "Qual evidência sustenta esta afirmação?", ask_role: "pesquisador" } : {}),
        ...(status === "disputed" ? { dispute_reason: reason } : {}),
      };
    }
    if (op === "resolve_missing") {
      return isHoursGap
        ? { kind: op, missing_id: missingId, formal_hours_event_ids: ids }
        : { kind: op, missing_id: missingId, evidence_ids: ids };
    }
    return { kind: op, description: text, outcome, evidence_ids: ids };
  };

  const submit = useMutation({
    mutationFn: () => api.post<{ new_version: { id: string } }>(`reports/${v.id}/review`, {
      decision: "changes_requested", comment: reason,
      correction: { reason, operations: [operation()] },
    }),
    onSuccess: (r) => onDone(r.new_version.id),
  });

  return (
    <form className="space-y-2 rounded border border-zinc-200 p-3" onSubmit={(e) => { e.preventDefault(); submit.mutate(); }}>
      <h3 className="text-sm font-medium">Corrigir (gera nova versão; a atual é preservada)</h3>
      <select className={inputClass} value={op} onChange={(e) => { const next = e.target.value as Op; setOp(next); setIds(next === "revise_claim" ? (v.draft.claims[v.claim_ids.indexOf(claimId)]?.evidence_ids ?? []) : []); setText(next === "revise_claim" ? (v.draft.claims[v.claim_ids.indexOf(claimId)]?.text ?? "") : ""); }}>
        <option value="revise_claim">Revisar uma afirmação</option>
        {v.missing_ids.length > 0 && <option value="resolve_missing">Resolver uma lacuna</option>}
        <option value="add_experiment">Acrescentar experimento</option>
      </select>
      {op === "revise_claim" && (
        <>
          <select className={inputClass} value={claimId} onChange={(e) => { setClaimId(e.target.value); const c = v.draft.claims[v.claim_ids.indexOf(e.target.value)]; setText(c?.text ?? ""); setIds(c?.evidence_ids ?? []); setStatus(c?.status ?? "supported"); }}>
            {v.claim_ids.map((id, i) => <option key={id} value={id}>{SECTION[v.draft.claims[i].section]} — {v.draft.claims[i].text.slice(0, 60)}</option>)}
          </select>
          <select className={inputClass} value={status} onChange={(e) => setStatus(e.target.value as ClaimStatus)}>
            <option value="supported">Com evidência</option><option value="pending">Pendente</option><option value="disputed">Em conflito</option>
          </select>
          <textarea className={inputClass} rows={2} placeholder="Novo texto" minLength={10} required value={text} onChange={(e) => setText(e.target.value)} />
        </>
      )}
      {op === "resolve_missing" && (
        <select className={inputClass} value={missingId} onChange={(e) => { setMissingId(e.target.value); setIds([]); }}>
          {v.missing_ids.map((id, i) => <option key={id} value={id}>{v.draft.missing[i].field}: {v.draft.missing[i].question}</option>)}
        </select>
      )}
      {op === "add_experiment" && (
        <>
          <input className={inputClass} placeholder="Descrição do experimento" minLength={10} required value={text} onChange={(e) => setText(e.target.value)} />
          <select className={inputClass} value={outcome} onChange={(e) => setOutcome(e.target.value as Outcome)}>
            {Object.entries(OUTCOME).map(([k, l]) => <option key={k} value={k}>{l}</option>)}
          </select>
        </>
      )}
      <EvidencePicker evidence={all} value={ids} onChange={setIds}
        filter={op === "resolve_missing" && isHoursGap ? (e) => e.kind === "formal_hours_declared" : (e) => e.kind !== "formal_hours_declared"} />
      <input className={inputClass} placeholder="Motivo da correção (obrigatório)" minLength={10} required value={reason} onChange={(e) => setReason(e.target.value)} />
      <button className={buttonClass} disabled={submit.isPending}>{submit.isPending ? "Enviando…" : "Gerar nova versão"}</button>
      {submit.isError && <ErrorBox error={submit.error} />}
    </form>
  );
}

export function ReportView({ ctx, current, canAct }: { ctx: DemoContext; current: ReportVersionOut; canAct: boolean }) {
  const queryClient = useQueryClient();
  const [selected, setSelected] = useState(current.version.id);
  const [conflict, setConflict] = useState<VersionConflict | null>(null);
  const history = useQuery({
    queryKey: ["history", current.version.id],
    queryFn: () => api.get<ReportVersionOut[]>(`reports/${current.version.id}/history`),
  });
  const evidence = useEvidence(ctx);
  const shown = history.data?.find((h) => h.version.id === selected) ?? current;
  const isOld = shown.version.id !== current.current_version_id;
  const refresh = () => {
    void queryClient.invalidateQueries({ queryKey: ["reports"] });
    void queryClient.invalidateQueries({ queryKey: ["history"] });
  };
  const confirm = useMutation({
    mutationFn: () => api.post(`reports/${shown.version.id}/review`, { decision: "text_approved" }),
    onSuccess: () => { setConflict(null); refresh(); },
    onError: (e) => { if (e instanceof ApiError && e.status === 409) setConflict(e.body as VersionConflict); },
  });
  const s = current.status;
  return (
    <Card
      title={`Relatório — versão atual v${s.current_version_number}`}
      actions={
        <div className="flex flex-wrap gap-1">
          <Badge tone={s.researcher.state === "text_approved" ? "ok" : "warn"}>Pesquisador: {REVIEW_STATE[s.researcher.state]}</Badge>
          <Badge tone={s.manager.state === "text_approved" ? "ok" : "neutral"}>Gerente: {REVIEW_STATE[s.manager.state]}</Badge>
          {s.approval_outdated && <Badge tone="warn">confirmação da v{s.approved_version_number} desatualizada</Badge>}
        </div>
      }
    >
      <div className="mb-3 flex flex-wrap items-center gap-2 text-sm">
        <span>Versões:</span>
        {history.isPending && <Loading />}
        {history.data?.map((h) => (
          <button key={h.version.id} type="button" onClick={() => { setSelected(h.version.id); setConflict(null); }}
            className={`rounded border px-2 py-0.5 ${h.version.id === shown.version.id ? "border-zinc-900 bg-zinc-900 text-white" : "border-zinc-300"}`}>
            v{h.version.number}{h.is_current ? " (atual)" : ""}
          </button>
        ))}
      </div>
      {isOld && <p className="mb-3 rounded border border-amber-200 bg-amber-50 p-2 text-sm text-amber-900">Você está vendo uma versão anterior (preservada). Confirmações valem só para a versão exata.</p>}
      <div className="grid gap-4 lg:grid-cols-[1fr_22rem]">
        <VersionBody out={shown} evidence={evidence.data ?? []} />
        <div className="space-y-4">
          <Checks versionId={shown.version.id} />
          {canAct && (
            <div className="space-y-2 rounded border border-zinc-200 p-3">
              <h3 className="text-sm font-medium">Confirmar texto da v{shown.version.number}</h3>
              <p className="text-xs text-zinc-500">Confirma redação e fatos desta versão exata. Não é aprovação fiscal.</p>
              <button type="button" className={buttonClass} onClick={() => confirm.mutate()} disabled={confirm.isPending}>
                {confirm.isPending ? "Confirmando…" : `Confirmar v${shown.version.number}`}
              </button>
              {conflict && (
                <div role="alert" className="rounded border border-amber-300 bg-amber-50 p-2 text-xs text-amber-900">
                  Conflito de versão (409): {conflict.detail}. Nada foi gravado.{" "}
                  <button type="button" className="underline" onClick={() => { setSelected(conflict.current_version_id); setConflict(null); }}>Abrir a versão atual</button>
                </div>
              )}
              {confirm.isError && !conflict && <ErrorBox error={confirm.error} />}
              {confirm.isSuccess && <p className="text-xs text-emerald-700">Texto da v{shown.version.number} confirmado.</p>}
            </div>
          )}
          {canAct && !isOld && <CorrectionForm key={shown.version.id} out={shown} ctx={ctx} onDone={(id) => { setSelected(id); refresh(); }} />}
        </div>
      </div>
    </Card>
  );
}
