"use client";
import { useState } from "react";
import { ShieldCheck } from "lucide-react";
import { useApp } from "@/store/AppContext";
import { resolveApproval } from "@/services/workflowEngine";
import { PageContainer } from "@/components/shared/PageContainer";
import {
  Intro,
  Empty,
  NativeSelect,
  Notice,
  GoLink,
} from "@/components/shared/WorkspaceUI";
import { StatusBadge } from "@/components/shared/StatusBadge";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { formatDate, getProjectIdentifier } from "@/components/shared/helpers";
import type { ApprovalRequest, ApprovalStatus } from "@/types";
function ApprovalCard({ approval }: { approval: ApprovalRequest }) {
  const { state, transact } = useApp();
  const [note, setNote] = useState("");
  const actionable =
    approval.status === "pending" || approval.status === "needs_revision";
  function decide(decision: ApprovalStatus) {
    transact(
      (s) => resolveApproval(s, approval.id, decision, note),
      decision === "approved"
        ? "Decisão registrada; a execução retomará com as políticas atuais."
        : decision === "needs_revision"
          ? "Complementação solicitada. Inclua a justificativa e reenvie para decisão."
          : "Decisão registrada",
    );
  }
  return (
    <Card>
      <CardContent className="space-y-4 pt-6">
        <div className="flex flex-wrap justify-between gap-3">
          <div>
            <p className="mb-1 text-xs text-muted-foreground">
              {approval.class} ·{" "}
              {getProjectIdentifier(state, approval.projectId)} ·{" "}
              {formatDate(approval.requestedAt)}
            </p>
            <h3 className="font-semibold">{approval.title}</h3>
          </div>
          <StatusBadge status={approval.status} />
        </div>
        <p className="text-sm text-muted-foreground">{approval.description}</p>
        <dl className="grid gap-3 rounded-lg bg-muted/50 p-4 text-xs sm:grid-cols-2">
          {approval.context.map((c, index) => (
            <div
              key={index}
              className={
                c.label === "Ação preparada"
                  ? "min-w-0 sm:col-span-2"
                  : "min-w-0"
              }
            >
              <dt className="font-semibold">{c.label}</dt>
              <dd className="mt-1 max-h-40 overflow-auto break-words whitespace-pre-wrap text-muted-foreground">
                {c.value}
              </dd>
            </div>
          ))}
        </dl>
        {approval.resolutionNote && (
          <p className="text-sm">
            Última decisão: {approval.resolutionNote} · {approval.resolvedBy} ·{" "}
            {formatDate(approval.resolvedAt)}
          </p>
        )}
        {actionable && (
          <>
            <label className="grid gap-2 text-sm font-medium">
              Justificativa / complementação
              <textarea
                className="field"
                value={note}
                onChange={(e) => setNote(e.target.value)}
                placeholder="Registre o contexto da decisão. Obrigatório para rejeitar, solicitar ajustes ou reenviar."
              />
            </label>
            <div className="flex flex-wrap gap-2">
              {approval.status === "needs_revision" ? (
                <Button
                  disabled={!note.trim()}
                  onClick={() => decide("pending")}
                >
                  Reenviar com complementação
                </Button>
              ) : (
                <>
                  <Button onClick={() => decide("approved")}>
                    <ShieldCheck className="mr-2 h-4 w-4" />
                    Aprovar ação preparada
                  </Button>
                  <Button
                    variant="destructive"
                    disabled={!note.trim()}
                    onClick={() => decide("rejected")}
                  >
                    Rejeitar
                  </Button>
                  <Button
                    variant="outline"
                    disabled={!note.trim()}
                    onClick={() => decide("needs_revision")}
                  >
                    Solicitar ajustes
                  </Button>
                </>
              )}
            </div>
          </>
        )}
        {approval.runId && (
          <GoLink href="/operacoes">Ver execução vinculada</GoLink>
        )}
      </CardContent>
    </Card>
  );
}
export default function ApprovalsPage() {
  const { state } = useApp();
  const [filter, setFilter] = useState("open");
  const rows = state.approvalRequests.filter(
    (a) =>
      filter === "all" ||
      (filter === "open"
        ? ["pending", "needs_revision"].includes(a.status)
        : a.status === filter),
  );
  return (
    <PageContainer>
      <Intro
        title="Decisões com contexto"
        description="Revise exceções e ações preparadas antes de liberar a próxima etapa."
      />
      <Notice>
        Aprovar autoriza somente a ação descrita. Bloqueios atuais continuam
        sendo verificados; uma decisão aqui não representa validação fiscal ou
        submissão oficial.
      </Notice>
      <NativeSelect
        aria-label="Filtrar aprovações"
        className="sm:max-w-64"
        value={filter}
        onChange={(e) => setFilter(e.target.value)}
      >
        <option value="open">Pendentes e em complementação</option>
        <option value="all">Todas as solicitações</option>
        <option value="approved">Aprovadas</option>
        <option value="rejected">Rejeitadas</option>
      </NativeSelect>
      {rows.map((approval) => (
        <ApprovalCard key={approval.id} approval={approval} />
      ))}
      {!rows.length && (
        <Empty text="Nenhuma solicitação neste filtro. Simule o cenário C na Central de Operações." />
      )}
    </PageContainer>
  );
}
