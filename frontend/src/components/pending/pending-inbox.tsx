"use client";

import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { TextField } from "@/components/forms/text-field";
import { EmptyState, ErrorState, LoadingState } from "@/components/status/states";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import type { PendingRequest, Role } from "@/lib/contracts/provisional";
import { queryKeys, usePendingFor, useRespondPending } from "@/lib/queries";

const ROLE_LABEL: Record<Role, string> = { researcher: "pesquisador", manager: "gerente", fiscal: "fiscal" };
const MIN_RESPONSE_LENGTH = 3;

function RespondForm({ request, personId }: { request: PendingRequest; personId: string }) {
  const [response, setResponse] = useState("");
  const respond = useRespondPending();
  const canSubmit = response.trim().length >= MIN_RESPONSE_LENGTH && !respond.isPending;

  return (
    <div className="space-y-2">
      <TextField
        label="Sua resposta (com a fonte, quando houver)"
        value={response}
        onChange={setResponse}
        placeholder={request.evidence_needed}
      />
      {respond.isError && <ErrorState error={respond.error} onRetry={() => respond.reset()} />}
      <Button
        disabled={!canSubmit}
        onClick={() => respond.mutate({ requestId: request.id, respondedBy: personId, response: response.trim() })}
      >
        {respond.isPending ? "Enviando…" : "Responder"}
      </Button>
    </div>
  );
}

/** Quando uma pendência respondida sai da lista (reanálise concluída), recarrega as telas afetadas. */
function useRefreshWhenResolved(requests: PendingRequest[] | undefined) {
  const client = useQueryClient();
  const answered = useRef<Set<string>>(new Set());

  useEffect(() => {
    if (!requests) return;
    const visible = new Set(requests.map((r) => r.id));
    const resolved = [...answered.current].some((id) => !visible.has(id));
    answered.current = new Set(requests.filter((r) => r.status === "answered").map((r) => r.id));
    if (resolved) void client.invalidateQueries({ queryKey: queryKeys.all });
  }, [requests, client]);
}

/** Pendências atribuídas a um papel. A resposta dispara reanálise no backend. */
export function PendingInbox({ role, personId }: { role: Role; personId: string }) {
  const pending = usePendingFor(role, personId);
  useRefreshWhenResolved(pending.data);

  if (pending.isPending) return <LoadingState label="Carregando pendências…" />;
  if (pending.isError) return <ErrorState error={pending.error} onRetry={() => pending.refetch()} />;
  if (pending.data.length === 0) return <EmptyState title="Nenhuma pendência para você." />;

  return (
    <div className="space-y-3">
      {pending.data.map((request) => (
        <Card key={request.id}>
          <CardHeader>
            <CardTitle className="flex flex-wrap items-center gap-2 text-base">
              {request.target.label}
              <Badge variant="outline">pedido pelo {ROLE_LABEL[request.requested_by_role]}</Badge>
            </CardTitle>
            <CardDescription>{request.reason}</CardDescription>
          </CardHeader>
          <CardContent className="space-y-2 text-sm">
            <p>
              <span className="font-medium">Evidência necessária:</span> {request.evidence_needed}
            </p>
            {request.status === "open" ? (
              <RespondForm request={request} personId={personId} />
            ) : (
              <p className="text-muted-foreground">
                Respondida: “{request.response}”. Aguardando reanálise.
              </p>
            )}
          </CardContent>
        </Card>
      ))}
    </div>
  );
}
