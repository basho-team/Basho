"use client";

import { useState } from "react";
import { TextField } from "@/components/forms/text-field";
import { ErrorState } from "@/components/status/states";
import { Button } from "@/components/ui/button";
import type { Claim } from "@/lib/contracts/provisional";
import { isVersionConflict, useSubmitCorrection } from "@/lib/queries";

/** Mesmo mínimo do backend para o motivo de uma correção (`MIN_REASON_LENGTH`). */
const MIN_JUSTIFICATION = 10;

interface CorrectionFormProps {
  claim: Claim;
  reportVersionId: string;
  /** Quem corrige (troca de papel da demonstração). */
  reviewerId: string;
  onDone: (newVersion: number) => void;
  onConflict: () => void;
}

/** Corrigir uma afirmação cria a versão N+1; a aprovação anterior não vale para ela. */
export function CorrectionForm({ claim, reportVersionId, reviewerId, onDone, onConflict }: CorrectionFormProps) {
  const [open, setOpen] = useState(false);
  const [text, setText] = useState(claim.text);
  const [justification, setJustification] = useState("");
  const correction = useSubmitCorrection();
  const valid = text.trim() !== claim.text && justification.trim().length >= MIN_JUSTIFICATION;

  if (!open) {
    return (
      <Button size="sm" variant="outline" onClick={() => setOpen(true)}>
        Corrigir
      </Button>
    );
  }

  return (
    <div className="space-y-2 rounded-md bg-muted/50 p-3">
      <TextField label="Texto corrigido" value={text} onChange={setText} rows={3} />
      <TextField
        label={`Por que corrigir? (obrigatório, ao menos ${MIN_JUSTIFICATION} caracteres)`}
        value={justification}
        onChange={setJustification}
        placeholder="Ex.: a integração foi na bancada B"
      />
      {correction.isError && !isVersionConflict(correction.error) && (
        <ErrorState error={correction.error} onRetry={() => correction.reset()} />
      )}
      <div className="flex gap-2">
        <Button
          size="sm"
          disabled={!valid || correction.isPending}
          onClick={() =>
            correction.mutate(
              {
                reportVersionId,
                reviewerId,
                role: "researcher",
                claimId: claim.id,
                newText: text.trim(),
                justification: justification.trim(),
              },
              {
                onSuccess: (detail) => onDone(detail.version.version),
                onError: (error) => {
                  if (isVersionConflict(error)) onConflict();
                },
              },
            )
          }
        >
          {correction.isPending ? "Salvando…" : "Salvar como nova versão"}
        </Button>
        <Button size="sm" variant="ghost" onClick={() => setOpen(false)}>
          Cancelar
        </Button>
      </div>
    </div>
  );
}
