"use client";

import { Send } from "lucide-react";
import { ErrorState } from "@/components/status/states";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import type { Consolidation } from "@/lib/contracts/provisional";
import { useForwardToFiscal } from "@/lib/queries";

const dateFormat = new Intl.DateTimeFormat("pt-BR", { dateStyle: "short", timeStyle: "short" });

/** O gate (`can_forward`) vem do backend; a UI só exibe os motivos de bloqueio. */
export function ForwardPanel({ consolidation }: { consolidation: Consolidation }) {
  const forward = useForwardToFiscal();

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Encaminhar ao fiscal</CardTitle>
        <CardDescription>
          {consolidation.forwarded_at
            ? `Último encaminhamento: ${dateFormat.format(new Date(consolidation.forwarded_at))}.`
            : "Ainda não encaminhado."}
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-3 text-sm">
        {consolidation.blocking_reasons.length > 0 && (
          <ul className="list-disc space-y-1 pl-5 text-muted-foreground">
            {consolidation.blocking_reasons.map((reason) => (
              <li key={reason}>{reason}</li>
            ))}
          </ul>
        )}
        {forward.isError && <ErrorState error={forward.error} onRetry={() => forward.reset()} />}
        <Button
          disabled={!consolidation.can_forward || forward.isPending}
          onClick={() => forward.mutate(consolidation.period_id)}
        >
          <Send aria-hidden />
          {forward.isPending ? "Encaminhando…" : "Encaminhar versões revisadas"}
        </Button>
      </CardContent>
    </Card>
  );
}
