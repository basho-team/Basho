"use client";

import { useState } from "react";
import { TextField } from "@/components/forms/text-field";
import { ErrorState } from "@/components/status/states";
import { Button } from "@/components/ui/button";
import type { FiscalDecision } from "@/lib/contracts/provisional";
import { useRecordFiscalDecision, useReturnPending } from "@/lib/queries";

const FISCAL_ID = "p-rafael";
const MIN_TEXT = 5;

const DECISIONS: { value: FiscalDecision["decision"]; label: string }[] = [
  { value: "agree", label: "Concordo" },
  { value: "disagree", label: "Discordo" },
  { value: "defer", label: "Adiar" },
];

export function DecisionForm({ findingId }: { findingId: string }) {
  const [decision, setDecision] = useState<FiscalDecision["decision"]>("agree");
  const [note, setNote] = useState("");
  const record = useRecordFiscalDecision();

  return (
    <div className="space-y-2">
      <div className="flex flex-wrap gap-1" role="radiogroup" aria-label="Decisão fiscal">
        {DECISIONS.map((d) => (
          <Button
            key={d.value}
            size="sm"
            role="radio"
            aria-checked={decision === d.value}
            variant={decision === d.value ? "default" : "outline"}
            onClick={() => setDecision(d.value)}
          >
            {d.label}
          </Button>
        ))}
      </div>
      <TextField label="Fundamento da decisão" value={note} onChange={setNote} />
      {record.isError && <ErrorState error={record.error} onRetry={() => record.reset()} />}
      <Button
        size="sm"
        disabled={note.trim().length < MIN_TEXT || record.isPending}
        onClick={() =>
          record.mutate(
            { findingId, decidedBy: FISCAL_ID, decision, note: note.trim() },
            { onSuccess: () => setNote("") },
          )
        }
      >
        {record.isPending ? "Registrando…" : "Registrar decisão"}
      </Button>
    </div>
  );
}

export function ReturnPendingForm({ findingId }: { findingId: string }) {
  const [assigneeRole, setAssigneeRole] = useState<"manager" | "researcher">("manager");
  const [reason, setReason] = useState("");
  const [evidenceNeeded, setEvidenceNeeded] = useState("");
  const giveBack = useReturnPending();
  const valid = reason.trim().length >= MIN_TEXT && evidenceNeeded.trim().length >= MIN_TEXT;

  return (
    <div className="space-y-2">
      <div className="flex flex-wrap gap-1" role="radiogroup" aria-label="Devolver para">
        {(["manager", "researcher"] as const).map((role) => (
          <Button
            key={role}
            size="sm"
            role="radio"
            aria-checked={assigneeRole === role}
            variant={assigneeRole === role ? "default" : "outline"}
            onClick={() => setAssigneeRole(role)}
          >
            {role === "manager" ? "Gerente" : "Pesquisador"}
          </Button>
        ))}
      </div>
      <TextField label="O que falta" value={reason} onChange={setReason} />
      <TextField label="Evidência necessária" value={evidenceNeeded} onChange={setEvidenceNeeded} />
      {giveBack.isError && <ErrorState error={giveBack.error} onRetry={() => giveBack.reset()} />}
      {giveBack.isSuccess && <p className="text-sm text-muted-foreground">Pendência enviada.</p>}
      <Button
        size="sm"
        variant="outline"
        disabled={!valid || giveBack.isPending}
        onClick={() =>
          giveBack.mutate(
            { findingId, assigneeRole, reason: reason.trim(), evidenceNeeded: evidenceNeeded.trim() },
            {
              onSuccess: () => {
                setReason("");
                setEvidenceNeeded("");
              },
            },
          )
        }
      >
        {giveBack.isPending ? "Enviando…" : "Devolver pendência"}
      </Button>
    </div>
  );
}
