"use client";
import { useState, type FormEvent } from "react";
import { Files, Pencil, FileCheck2 } from "lucide-react";
import { useApp } from "@/store/AppContext";
import { completeness, makeDocument } from "@/services/simulationService";
import { PageContainer } from "@/components/shared/PageContainer";
import {
  Intro,
  Field,
  NativeSelect,
  Notice,
  GoLink,
  Modal,
  Submit,
} from "@/components/shared/WorkspaceUI";
import { StatusBadge } from "@/components/shared/StatusBadge";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Progress } from "@/components/ui/progress";
import { formatDate } from "@/components/shared/helpers";
import type { DocumentStatus, LeiDoBemDocumentItem } from "@/types";
const STATUSES: Record<DocumentStatus, string> = {
  present: "Documento presente",
  absent: "Documento ausente",
  draft: "Em elaboração",
  pending_review: "Pendente de revisão",
  validated: "Validado por responsável",
};
export default function LeiDoBemPage() {
  const { state, execute } = useApp();
  const [projectId, setProjectId] = useState(state.projects[0].id),
    [editing, setEditing] = useState<LeiDoBemDocumentItem | null>(null);
  const project = state.projects.find((p) => p.id === projectId)!;
  const items = state.leiDoBemItems.filter((i) => i.projectId === projectId),
    documents = state.driveItems.filter(
      (d) => d.projectId === projectId && d.type === "file",
    );
  const percent = completeness(state, projectId),
    missing = items.filter((i) => i.status === "absent").length;
  function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!editing) return;
    const form = new FormData(event.currentTarget);
    if (
      execute({
        kind: "checklist.update",
        id: editing.id,
        status: String(form.get("status")) as DocumentStatus,
        documentId: String(form.get("document")) || undefined,
        validatedBy: String(form.get("responsible")) || undefined,
      })
    )
      setEditing(null);
  }
  function dossier() {
    const folder = state.driveItems.find(
      (d) =>
        d.type === "folder" &&
        d.projectId === projectId &&
        d.name === "Relatórios Técnicos",
    );
    const content = `# Estrutura preliminar FORMP&D — ${project.identifier}\n\nAMBIENTE DE DEMONSTRAÇÃO — DADOS SINTÉTICOS\nRascunho para organização documental. Não é formulário oficial.\n\n## Projeto\n${project.name}\n${project.description}\n\n## Objetivos\n${project.objectives}\n\n## Índice documental\n${items.map((i) => `- ${i.label}: ${STATUSES[i.status]} — ${i.documentId ?? "sem documento vinculado"}`).join("\n")}\n\n## Pendências\n${project.pendingItems.map((p) => `- ${p}`).join("\n")}\n\nPreenchimento definitivo, validação regulatória e submissão oficial dependem de etapas futuras fora desta demonstração.`;
    execute({
      kind: "drive.create",
      item: makeDocument(
        `Estrutura preliminar FORMP&D — ${Date.now()}.md`,
        folder?.id ?? project.driveFolderIds[0],
        projectId,
        content,
        "report",
      ),
    });
  }
  return (
    <PageContainer>
      <Intro
        eyebrow="PREPARAÇÃO DOCUMENTAL"
        title="Lei do Bem e FORMP&D"
        description="Organize informações técnicas e comprovantes com critérios explícitos de presença e revisão."
      >
        <Button onClick={dossier}>
          <Files className="mr-2 h-4 w-4" />
          Gerar estrutura preliminar
        </Button>
      </Intro>
      <Notice>
        A completude mede organização documental. Evidências isoladas não
        comprovam elegibilidade. A demonstração não decide enquadramento fiscal
        nem preenche ou submete o formulário oficial.
      </Notice>
      <NativeSelect
        className="sm:max-w-xl"
        aria-label="Projeto do dossiê"
        value={projectId}
        onChange={(e) => setProjectId(e.target.value)}
      >
        {state.projects.map((p) => (
          <option key={p.id} value={p.id}>
            {p.identifier} — {p.name}
          </option>
        ))}
      </NativeSelect>
      <div className="grid gap-4 md:grid-cols-3">
        <Card className="md:col-span-2">
          <CardContent className="space-y-4 pt-6">
            <div className="flex justify-between">
              <p className="font-medium">Completude documental</p>
              <p className="font-semibold text-emerald-800">{percent}%</p>
            </div>
            <Progress value={percent} />
            <p className="text-xs leading-relaxed text-muted-foreground">
              Critério: itens presentes ou validados com documento vinculado ao
              projeto. Objetivos podem ser atendidos pelo campo do projeto.
              Rascunhos e documentos sem vínculo não contam como completos.
            </p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-6">
            <FileCheck2 className="mb-3 h-5 w-5 text-emerald-700" />
            <p className="text-2xl font-semibold">{missing}</p>
            <p className="text-sm text-muted-foreground">
              itens documentais ausentes
            </p>
          </CardContent>
        </Card>
      </div>
      <Card className="overflow-x-auto">
        <table className="data-table">
          <thead>
            <tr>
              <th>Informação / documento</th>
              <th>Estado documental</th>
              <th>Validação / ações</th>
            </tr>
          </thead>
          <tbody>
            {items.map((item) => (
              <tr key={item.id}>
                <td>
                  <p className="font-medium">{item.label}</p>
                  {item.documentId ? (
                    <GoLink href={`/documentos?arquivo=${item.documentId}`}>
                      {documents.find((d) => d.id === item.documentId)?.name ??
                        "Documento vinculado"}
                    </GoLink>
                  ) : (
                    <p className="mt-1 text-xs text-muted-foreground">
                      {item.type === "objectives"
                        ? project.objectives
                        : "Sem documento vinculado"}
                    </p>
                  )}
                </td>
                <td>
                  <StatusBadge status={item.status} />
                </td>
                <td>
                  <p className="mb-2 text-xs text-muted-foreground">
                    {item.validatedBy ?? "Sem validação humana"}
                    <br />
                    {formatDate(item.lastModified ?? null)}
                  </p>
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => setEditing(item)}
                  >
                    <Pencil className="mr-2 h-3 w-3" />
                    Atualizar item
                  </Button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>
      <Card>
        <CardContent className="space-y-4 pt-6">
          <h3 className="font-semibold">Preparação futura do dossiê FORMP&D</h3>
          <p className="text-sm text-muted-foreground">
            A estrutura preliminar reúne identificação, objetivos, índice
            documental e pendências. O arquivo gerado fica no Drive simulado do
            projeto para revisão do responsável.
          </p>
          <GoLink href={`/documentos?projeto=${projectId}`}>
            Consultar estruturas e relatórios gerados
          </GoLink>
        </CardContent>
      </Card>
      <Modal
        title="Atualizar item documental"
        open={!!editing}
        onClose={() => setEditing(null)}
      >
        {editing && (
          <form onSubmit={save} className="space-y-4">
            <p className="font-medium">{editing.label}</p>
            <Field label="Estado documental">
              <NativeSelect name="status" defaultValue={editing.status}>
                {Object.entries(STATUSES).map(([id, label]) => (
                  <option key={id} value={id}>
                    {label}
                  </option>
                ))}
              </NativeSelect>
            </Field>
            <Field label="Documento comprobatório do projeto">
              <NativeSelect
                name="document"
                defaultValue={editing.documentId ?? ""}
              >
                <option value="">Nenhum documento vinculado</option>
                {documents.map((d) => (
                  <option key={d.id} value={d.id}>
                    {d.name}
                  </option>
                ))}
              </NativeSelect>
            </Field>
            <Field label="Responsável pela validação (obrigatório para validar)">
              <Input name="responsible" defaultValue={editing.validatedBy} />
            </Field>
            <Submit />
          </form>
        )}
      </Modal>
    </PageContainer>
  );
}
