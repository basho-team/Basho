"use client";

import { useState } from "react";
import { TextField } from "@/components/forms/text-field";
import { ErrorState } from "@/components/status/states";
import { Button } from "@/components/ui/button";
import { useRequestClarification } from "@/lib/queries";

const MIN_QUESTION = 5;

export function ClarificationForm({ reportId, authorName }: { reportId: string; authorName: string }) {
  const [open, setOpen] = useState(false);
  const [question, setQuestion] = useState("");
  const clarification = useRequestClarification();

  if (!open) {
    return (
      <Button size="sm" variant="outline" onClick={() => setOpen(true)}>
        Pedir esclarecimento
      </Button>
    );
  }

  return (
    <div className="space-y-2">
      <TextField label={`Pergunta para ${authorName}`} value={question} onChange={setQuestion} />
      {clarification.isError && <ErrorState error={clarification.error} onRetry={() => clarification.reset()} />}
      <div className="flex gap-2">
        <Button
          size="sm"
          disabled={question.trim().length < MIN_QUESTION || clarification.isPending}
          onClick={() =>
            clarification.mutate(
              { reportId, question: question.trim() },
              {
                onSuccess: () => {
                  setQuestion("");
                  setOpen(false);
                },
              },
            )
          }
        >
          {clarification.isPending ? "Enviando…" : "Enviar"}
        </Button>
        <Button size="sm" variant="ghost" onClick={() => setOpen(false)}>
          Cancelar
        </Button>
      </div>
    </div>
  );
}
