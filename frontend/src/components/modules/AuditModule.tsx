"use client";
import { useState } from "react";
import { useSearchParams } from "next/navigation";
import { useApp } from "@/store/AppContext";
import { PageContainer } from "@/components/shared/PageContainer";
import {
  Intro,
  SearchBox,
  NativeSelect,
  Empty,
} from "@/components/shared/WorkspaceUI";
import { Card } from "@/components/ui/card";
import { formatDate } from "@/components/shared/helpers";
export default function AuditModule() {
  const { state } = useApp();
  const params = useSearchParams();
  const [query, setQuery] = useState(""),
    [origin, setOrigin] = useState(""),
    [result, setResult] = useState(""),
    [execution, setExecution] = useState(params.get("execucao") ?? "");
  const rows = state.auditLogs.filter(
    (log) =>
      (!origin || log.eventOrigin === origin) &&
      (!result || log.result === result) &&
      (!execution || log.executionId === execution) &&
      `${log.operation} ${log.resourceAffected} ${log.actor} ${log.justification ?? ""}`
        .toLowerCase()
        .includes(query.toLowerCase()),
  );
  return (
    <PageContainer>
      <Intro
        title="Cada operação deixa um registro"
        description="Consulte a origem, a decisão de permissão e os dados anteriores e posteriores de cada ação."
      />
      <div className="flex flex-wrap gap-3">
        <SearchBox
          value={query}
          onChange={setQuery}
          placeholder="Pesquisar operação, recurso ou responsável…"
        />
        <NativeSelect
          className="sm:max-w-44"
          aria-label="Origem do registro"
          value={origin}
          onChange={(e) => setOrigin(e.target.value)}
        >
          <option value="">Todas as origens</option>
          {[...new Set(state.auditLogs.map((l) => l.eventOrigin))].map((o) => (
            <option key={o}>{o}</option>
          ))}
        </NativeSelect>
        <NativeSelect
          className="sm:max-w-44"
          aria-label="Resultado da operação"
          value={result}
          onChange={(e) => setResult(e.target.value)}
        >
          <option value="">Todos os resultados</option>
          {[...new Set(state.auditLogs.map((l) => l.result))].map((r) => (
            <option key={r}>{r}</option>
          ))}
        </NativeSelect>
        <NativeSelect
          className="sm:max-w-64"
          aria-label="Filtrar por execução"
          value={execution}
          onChange={(e) => setExecution(e.target.value)}
        >
          <option value="">Todas as execuções</option>
          {state.agentRuns.map((r) => (
            <option key={r.id} value={r.id}>
              {r.id}
            </option>
          ))}
        </NativeSelect>
      </div>
      <p className="text-xs text-muted-foreground">
        {rows.length} registros · somente acréscimo durante a demonstração ·
        horários de Fortaleza (UTC−3)
      </p>
      <Card className="overflow-x-auto">
        <table className="data-table">
          <thead>
            <tr>
              <th>Data / origem</th>
              <th>Operação / recurso</th>
              <th>Responsável / resultado</th>
              <th>Rastreabilidade</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((log) => (
              <tr key={log.id}>
                <td className="min-w-40 text-xs">
                  {formatDate(log.timestamp)}
                  <p className="mt-1 text-muted-foreground">
                    {log.eventOrigin}
                  </p>
                </td>
                <td>
                  <p className="font-medium">{log.operation}</p>
                  <p className="mt-1 max-w-72 break-all text-xs text-muted-foreground">
                    {log.resourceAffected}
                  </p>
                </td>
                <td className="text-xs">
                  {log.actor}
                  <p className="mt-1 text-muted-foreground">{log.result}</p>
                </td>
                <td>
                  <details className="min-w-48 text-xs">
                    <summary>Ver decisão e alterações</summary>
                    <div className="mt-3 max-w-xl space-y-3">
                      <p className="break-all">
                        ID: {log.id}
                        <br />
                        Execução: {log.executionId ?? "Operação direta"}
                      </p>
                      <p>
                        Política:{" "}
                        {log.policyApplied ??
                          "Configuração humana / registro de evento"}
                      </p>
                      <p>
                        {log.justification ??
                          "Registro operacional da demonstração"}
                      </p>
                      <p className="font-medium">Estado anterior</p>
                      <pre className="max-h-48 overflow-auto whitespace-pre-wrap rounded bg-muted p-3">
                        {log.previousState ?? "Não aplicável"}
                      </pre>
                      <p className="font-medium">Estado posterior</p>
                      <pre className="max-h-48 overflow-auto whitespace-pre-wrap rounded bg-muted p-3">
                        {log.newState ?? "Não aplicável"}
                      </pre>
                    </div>
                  </details>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {!rows.length && (
          <Empty text="Nenhum registro neste filtro. Configure uma integração ou execute uma simulação." />
        )}
      </Card>
    </PageContainer>
  );
}
