"use client";

import { IntegrationsPanel } from "@/components/integrations/integrations-panel";
import { PageHeader } from "@/components/layout/page-header";
import { EmptyState } from "@/components/status/states";
import { publicEnv } from "@/lib/env";

export default function IntegracoesPage() {
  const projectId = publicEnv.NEXT_PUBLIC_BASHO_PROJECT_ID;
  const live = publicEnv.NEXT_PUBLIC_DATA_SOURCE === "api" && projectId !== undefined;
  return (
    <div className="space-y-6">
      <PageHeader
        title="Integrações"
        subtitle="Cole um link com permissão de edição e o Basho gera e organiza os relatórios na pasta BASHO."
      />
      {live ? (
        <IntegrationsPanel projectId={projectId} />
      ) : (
        <EmptyState title="Disponível só com o backend real">
          Rode com <code>NEXT_PUBLIC_DATA_SOURCE=api</code> e <code>NEXT_PUBLIC_BASHO_PROJECT_ID</code> (veja{" "}
          <code>docs/demo.md</code>).
        </EmptyState>
      )}
    </div>
  );
}
