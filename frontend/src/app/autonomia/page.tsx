"use client";
import { useState } from "react";
import { Shield } from "lucide-react";
import { useApp } from "@/store/AppContext";
import {
  checkPermission,
  POLICY_LABELS,
  PROVIDER_LABELS,
} from "@/services/permissionService";
import { setPolicy } from "@/services/settingsService";
import { PageContainer } from "@/components/shared/PageContainer";
import {
  Intro,
  Field,
  NativeSelect,
  Notice,
} from "@/components/shared/WorkspaceUI";
import { Card } from "@/components/ui/card";
import { StatusBadge } from "@/components/shared/StatusBadge";
import type { IntegrationProvider, PermissionLevel } from "@/types";
export default function AutonomyPage() {
  const { state, transact } = useApp();
  const [provider, setProvider] = useState<IntegrationProvider>("google_drive"),
    [project, setProject] = useState(""),
    [resource, setResource] = useState("");
  const policies = state.permissionPolicies.filter(
    (p) => p.provider === provider && !p.projectId && !p.resourceId,
  );
  const resources = (
    provider === "google_drive"
      ? state.driveItems
      : provider === "notion"
        ? state.activities
        : state.githubRepos
  )
    .filter((r) => !project || r.projectId === project)
    .map((r) => ({ id: r.id, label: "name" in r ? r.name : r.title }));
  return (
    <PageContainer>
      <Intro
        title="Autonomia com limites claros"
        description="Defina quais operações podem avançar, quais exigem uma decisão e quais ficam bloqueadas."
      />
      <Notice>
        Políticas mais específicas prevalecem: recurso → projeto → integração.
        Operações formais e alterações de originais permanecem bloqueadas. O
        acesso também depende da conexão e do escopo selecionado em Integrações.
      </Notice>
      <div className="grid gap-4 rounded-xl border bg-card p-5 md:grid-cols-3">
        <Field label="Integração">
          <NativeSelect
            value={provider}
            onChange={(e) => {
              setProvider(e.target.value as IntegrationProvider);
              setResource("");
            }}
          >
            {Object.entries(PROVIDER_LABELS).map(([id, label]) => (
              <option key={id} value={id}>
                {label}
              </option>
            ))}
          </NativeSelect>
        </Field>
        <Field label="Escopo de projeto">
          <NativeSelect
            value={project}
            onChange={(e) => {
              setProject(e.target.value);
              setResource("");
            }}
          >
            <option value="">Todos os projetos</option>
            {state.projects.map((p) => (
              <option key={p.id} value={p.id}>
                {p.identifier} — {p.name}
              </option>
            ))}
          </NativeSelect>
        </Field>
        <Field label="Recurso">
          <NativeSelect
            value={resource}
            onChange={(e) => setResource(e.target.value)}
          >
            <option value="">Todos os recursos do escopo</option>
            {resources.map((r) => (
              <option key={r.id} value={r.id}>
                {r.label}
              </option>
            ))}
          </NativeSelect>
        </Field>
      </div>
      <Card className="overflow-x-auto">
        <table className="data-table">
          <thead>
            <tr>
              <th>Operação</th>
              <th>Política efetiva</th>
              <th>Configuração neste escopo</th>
            </tr>
          </thead>
          <tbody>
            {policies.map((policy) => {
              const effective = checkPermission(
                  state.permissionPolicies,
                  provider,
                  policy.operation,
                  project || undefined,
                  resource || undefined,
                ),
                specific = state.permissionPolicies.find(
                  (p) =>
                    p.provider === provider &&
                    p.operation === policy.operation &&
                    p.projectId === (project || undefined) &&
                    p.resourceId === (resource || undefined),
                );
              return (
                <tr key={policy.id}>
                  <td>
                    <p className="font-medium">{policy.label}</p>
                    <p className="mt-1 text-xs text-muted-foreground">
                      {policy.description}
                    </p>
                    <p className="mt-1 font-mono text-[10px] text-muted-foreground">
                      {policy.category}
                    </p>
                  </td>
                  <td>
                    <StatusBadge status={effective.level} />
                    <p className="mt-2 text-xs text-muted-foreground">
                      {specific
                        ? "Definida neste escopo"
                        : "Herdada de escopo superior"}
                    </p>
                  </td>
                  <td>
                    <NativeSelect
                      aria-label={`Política para ${policy.label}`}
                      disabled={policy.category === "formal"}
                      value={effective.level}
                      onChange={(e) =>
                        transact(
                          (s) =>
                            setPolicy(
                              s,
                              policy,
                              e.target.value as PermissionLevel,
                              project || undefined,
                              resource || undefined,
                            ),
                          "Política salva. As próximas etapas usarão esta configuração.",
                        )
                      }
                    >
                      {Object.entries(POLICY_LABELS).map(([id, label]) => (
                        <option key={id} value={id}>
                          {label}
                        </option>
                      ))}
                    </NativeSelect>
                    {policy.category === "formal" && (
                      <p className="mt-2 flex items-center gap-1 text-xs text-muted-foreground">
                        <Shield className="h-3 w-3" />
                        Bloqueio permanente nesta etapa
                      </p>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </Card>
    </PageContainer>
  );
}
