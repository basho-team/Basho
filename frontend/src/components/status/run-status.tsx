"use client";

import { useQueryClient } from "@tanstack/react-query";
import { Loader2 } from "lucide-react";
import { useEffect, useRef } from "react";
import { RunStatusBadge } from "@/components/status/badges";
import type { Run } from "@/lib/contracts/provisional";
import { isRunActive, queryKeys } from "@/lib/queries";

/** Mostra o estado da execução. Ao terminar, recarrega as telas afetadas. */
export function RunStatus({ run }: { run: Run }) {
  const client = useQueryClient();
  const wasActive = useRef(isRunActive(run));

  useEffect(() => {
    const active = isRunActive(run);
    if (wasActive.current && !active) {
      void client.invalidateQueries({ queryKey: queryKeys.all });
    }
    wasActive.current = active;
  }, [run, client]);

  return (
    <div role="status" aria-live="polite" className="flex flex-wrap items-center gap-2 text-sm">
      {isRunActive(run) && <Loader2 className="size-4 animate-spin" aria-hidden />}
      <RunStatusBadge status={run.status} />
      <span className="text-muted-foreground">{run.message}</span>
      {run.error && <span className="text-destructive">{run.error.message}</span>}
    </div>
  );
}
