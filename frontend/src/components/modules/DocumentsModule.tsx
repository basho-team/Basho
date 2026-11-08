"use client";
import { useState, type FormEvent } from "react";
import { useSearchParams } from "next/navigation";
import {
  FileText,
  Folder,
  LockKeyhole,
  Plus,
  FolderPlus,
  ChevronRight,
  Copy,
  Move,
  Pencil,
  Eye,
} from "lucide-react";
import { useApp } from "@/store/AppContext";
import { PageContainer } from "@/components/shared/PageContainer";
import {
  Intro,
  Field,
  NativeSelect,
  Modal,
  SearchBox,
  Empty,
  Notice,
  Submit,
} from "@/components/shared/WorkspaceUI";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import {
  CATEGORY_LABELS,
  formatDate,
  getProjectIdentifier,
} from "@/components/shared/helpers";
import { makeDocument, timestamp, uid } from "@/services/simulationService";
import type { DocumentCategory, DriveItem } from "@/types";

type FileAction = {
  kind: "file" | "folder" | "rename" | "move" | "copy" | "preview";
  item?: DriveItem;
};
const ACTION_LABELS = {
  file: "Criar arquivo",
  folder: "Criar pasta",
  rename: "Renomear",
  move: "Mover recurso",
  copy: "Criar cópia de trabalho",
  preview: "Visualizar documento",
};
function folderDepth(items: DriveItem[], item: DriveItem): number {
  let depth = 0,
    current = item;
  const visited = new Set<string>();
  while (current.parentId && !visited.has(current.id)) {
    visited.add(current.id);
    depth++;
    const parent = items.find((i) => i.id === current.parentId);
    if (!parent) break;
    current = parent;
  }
  return depth;
}
export default function DocumentsModule() {
  const { state, execute } = useApp();
  const params = useSearchParams();
  const [parentId, setParentId] = useState("drive-folder-root");
  const [project, setProject] = useState(params.get("projeto") ?? "");
  const [query, setQuery] = useState("");
  const [category, setCategory] = useState("");
  const [action, setAction] = useState<FileAction | null>(() => {
    const item = state.driveItems.find((d) => d.id === params.get("arquivo"));
    return item ? { kind: "preview", item } : null;
  });
  const folders = state.driveItems.filter((d) => d.type === "folder");
  const all = !!query || !!category || !!project;
  const items = state.driveItems
    .filter(
      (d) =>
        (all ? d.type === "file" : d.parentId === parentId) &&
        (!project || d.projectId === project) &&
        (!category || d.category === category) &&
        (!query ||
          d.name.toLocaleLowerCase().includes(query.toLocaleLowerCase())),
    )
    .sort((a, b) =>
      a.type === b.type
        ? a.name.localeCompare(b.name)
        : a.type === "folder"
          ? -1
          : 1,
    );
  const current = state.driveItems.find((d) => d.id === parentId);
  const breadcrumbs: DriveItem[] = [];
  let cursor = current;
  const visited = new Set<string>();
  while (cursor && !visited.has(cursor.id)) {
    visited.add(cursor.id);
    breadcrumbs.unshift(cursor);
    cursor = state.driveItems.find((d) => d.id === cursor?.parentId);
  }
  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!action) return;
    const form = new FormData(event.currentTarget),
      name = String(form.get("name") ?? "").trim(),
      destination = String(form.get("destination") ?? parentId),
      projectId = String(
        form.get("project") ??
          action.item?.projectId ??
          current?.projectId ??
          state.projects[0].id,
      );
    let accepted = false;
    if (action.kind === "file" || action.kind === "folder") {
      const item = makeDocument(
        name,
        destination,
        projectId,
        String(form.get("content") ?? ""),
        String(form.get("category") ?? "technical_doc") as DocumentCategory,
      );
      if (action.kind === "folder") {
        item.type = "folder";
        item.mimeType = "application/vnd.google-apps.folder";
        delete item.category;
      }
      accepted = execute({ kind: "drive.create", item });
    } else if (action.item && action.kind === "copy")
      accepted = execute({
        kind: "drive.copy",
        sourceId: action.item.id,
        item: {
          ...action.item,
          id: uid("copy"),
          name,
          parentId: destination,
          isOriginal: false,
          isProtected: false,
          derivedFromId: action.item.id,
          createdAt: timestamp(),
          modifiedAt: timestamp(),
          createdBy: "user",
        },
      });
    else if (action.item)
      accepted = execute({
        kind: "drive.update",
        id: action.item.id,
        patch: action.kind === "rename" ? { name } : { parentId: destination },
      });
    if (accepted) setAction(null);
  }
  return (
    <PageContainer>
      <Intro
        title="Documentos e evidências"
        description="Uma base organizada, com origem, contexto e vínculo com cada projeto."
      >
        <div className="flex gap-2">
          <Button
            variant="outline"
            onClick={() => setAction({ kind: "folder" })}
          >
            <FolderPlus className="mr-2 h-4 w-4" />
            Nova pasta
          </Button>
          <Button onClick={() => setAction({ kind: "file" })}>
            <Plus className="mr-2 h-4 w-4" />
            Novo arquivo
          </Button>
        </div>
      </Intro>
      <Notice>
        Google Drive simulado. Contratos, notas fiscais e demais originais são
        preservados. Use cópias de trabalho para derivar novos documentos.
      </Notice>
      <Card className="overflow-hidden">
        <div className="flex flex-wrap gap-3 border-b p-4">
          <SearchBox
            value={query}
            onChange={setQuery}
            placeholder="Pesquisar em todos os arquivos…"
          />
          <NativeSelect
            aria-label="Filtrar por projeto"
            className="sm:max-w-56"
            value={project}
            onChange={(e) => setProject(e.target.value)}
          >
            <option value="">Todos os projetos</option>
            {state.projects.map((p) => (
              <option key={p.id} value={p.id}>
                {p.identifier}
              </option>
            ))}
          </NativeSelect>
          <NativeSelect
            aria-label="Filtrar por categoria"
            className="sm:max-w-52"
            value={category}
            onChange={(e) => setCategory(e.target.value)}
          >
            <option value="">Todas as categorias</option>
            {Object.entries(CATEGORY_LABELS).map(([id, label]) => (
              <option key={id} value={id}>
                {label}
              </option>
            ))}
          </NativeSelect>
        </div>
        <div className="grid md:grid-cols-[230px_1fr]">
          <aside
            className="max-h-72 overflow-auto border-b bg-muted/20 p-3 md:max-h-none md:border-r md:border-b-0"
            aria-label="Pastas do Drive"
          >
            {folders.map((folder) => (
              <button
                key={folder.id}
                onClick={() => {
                  setParentId(folder.id);
                  setQuery("");
                  setProject("");
                  setCategory("");
                }}
                style={{
                  paddingLeft: `${8 + folderDepth(state.driveItems, folder) * 10}px`,
                }}
                className={`flex w-full items-center gap-2 rounded-md py-2 text-left text-xs ${folder.id === parentId ? "bg-emerald-100 text-emerald-950" : "text-muted-foreground hover:bg-muted"}`}
              >
                <Folder className="h-3.5 w-3.5 shrink-0" />
                <span className="break-words">{folder.name}</span>
              </button>
            ))}
          </aside>
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-1 border-b px-4 py-3 text-xs text-muted-foreground">
              {all
                ? "Resultados em todos os diretórios"
                : breadcrumbs.map((f) => (
                    <span className="inline-flex items-center" key={f.id}>
                      <ChevronRight className="h-3 w-3" />
                      <button
                        onClick={() => setParentId(f.id)}
                        className="hover:underline"
                      >
                        {f.name}
                      </button>
                    </span>
                  ))}
            </div>
            <div className="overflow-x-auto">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Nome do recurso</th>
                    <th>Projeto / categoria</th>
                    <th>Operações</th>
                  </tr>
                </thead>
                <tbody>
                  {items.map((item) => (
                    <tr key={item.id}>
                      <td>
                        <button
                          className="flex items-center gap-3 text-left font-medium hover:text-emerald-700"
                          onClick={() =>
                            item.type === "folder"
                              ? setParentId(item.id)
                              : setAction({ kind: "preview", item })
                          }
                        >
                          {item.type === "folder" ? (
                            <Folder className="h-5 w-5 shrink-0 text-emerald-700" />
                          ) : (
                            <FileText className="h-5 w-5 shrink-0 text-slate-400" />
                          )}
                          {item.name}
                        </button>
                        <p className="mt-2 flex items-center gap-1 text-xs text-muted-foreground">
                          {item.isProtected && (
                            <LockKeyhole className="h-3 w-3" />
                          )}
                          {item.isOriginal ? "Original preservado" : "Derivado"}{" "}
                          · {formatDate(item.modifiedAt)}
                        </p>
                      </td>
                      <td className="text-xs text-muted-foreground">
                        {getProjectIdentifier(state, item.projectId)}
                        <p className="mt-1">
                          {CATEGORY_LABELS[item.category ?? ""] ?? "Pasta"}
                        </p>
                      </td>
                      <td>
                        <div className="flex gap-1">
                          {item.type === "file" && (
                            <Button
                              variant="ghost"
                              size="icon"
                              aria-label={`Visualizar ${item.name}`}
                              onClick={() =>
                                setAction({ kind: "preview", item })
                              }
                            >
                              <Eye className="h-4 w-4" />
                            </Button>
                          )}
                          <Button
                            variant="ghost"
                            size="icon"
                            aria-label={`Renomear ${item.name}`}
                            onClick={() => setAction({ kind: "rename", item })}
                          >
                            <Pencil className="h-4 w-4" />
                          </Button>
                          <Button
                            variant="ghost"
                            size="icon"
                            aria-label={`Mover ${item.name}`}
                            onClick={() => setAction({ kind: "move", item })}
                          >
                            <Move className="h-4 w-4" />
                          </Button>
                          {item.type === "file" && (
                            <Button
                              variant="ghost"
                              size="icon"
                              aria-label={`Copiar ${item.name}`}
                              onClick={() => setAction({ kind: "copy", item })}
                            >
                              <Copy className="h-4 w-4" />
                            </Button>
                          )}
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {!items.length && (
                <Empty text="Pasta vazia ou nenhum arquivo corresponde aos filtros." />
              )}
            </div>
          </div>
        </div>
      </Card>
      <Card>
        <CardContent className="pt-6">
          <h3 className="mb-4 font-semibold">
            Registro de evidências ·{" "}
            {
              state.evidence.filter((e) => !project || e.projectId === project)
                .length
            }
          </h3>
          {state.evidence
            .filter((e) => !project || e.projectId === project)
            .map((e) => (
              <details key={e.id} className="border-t py-3 text-sm">
                <summary>
                  {e.claim} · {getProjectIdentifier(state, e.projectId)}
                </summary>
                <div className="space-y-2 pt-3 text-xs text-muted-foreground">
                  <p>{e.reason}</p>
                  <p>
                    ID: {e.id} · Fonte: {e.source} · Referência: {e.sourceRef}
                  </p>
                  <p>
                    {formatDate(e.createdAt)} · Estado: {e.status}
                  </p>
                </div>
              </details>
            ))}
          {!state.evidence.length && (
            <Empty text="Execute o cenário A para registrar evidências técnicas." />
          )}
        </CardContent>
      </Card>
      <Modal
        open={!!action}
        title={action ? ACTION_LABELS[action.kind] : "Documento"}
        onClose={() => setAction(null)}
      >
        {action?.kind === "preview" ? (
          <>
            <p className="font-medium">{action.item?.name}</p>
            <p className="text-xs text-muted-foreground">
              ID: {action.item?.id} ·{" "}
              {action.item?.isProtected
                ? "Original protegido"
                : "Documento derivado"}
            </p>
            <pre className="max-h-96 overflow-auto whitespace-pre-wrap rounded-lg bg-muted p-4 text-sm">
              {action.item?.content ??
                "Prévia sintética: este arquivo representa um documento fictício. Nenhum documento pessoal ou empresarial foi utilizado."}
            </pre>
          </>
        ) : (
          action && (
            <form onSubmit={submit} className="space-y-4">
              {action.kind !== "move" && (
                <Field label="Nome">
                  <Input
                    name="name"
                    required
                    maxLength={180}
                    defaultValue={
                      action.kind === "copy"
                        ? `Cópia — ${action.item?.name}`
                        : (action.item?.name ?? "")
                    }
                  />
                </Field>
              )}
              {action.kind !== "rename" && (
                <Field label="Pasta de destino">
                  <NativeSelect name="destination" defaultValue={parentId}>
                    {folders.map((f) => (
                      <option key={f.id} value={f.id}>
                        {f.name}
                      </option>
                    ))}
                  </NativeSelect>
                </Field>
              )}
              {["file", "folder"].includes(action.kind) && (
                <Field label="Projeto associado">
                  <NativeSelect
                    name="project"
                    defaultValue={
                      current?.projectId ?? project ?? state.projects[0].id
                    }
                  >
                    {state.projects.map((p) => (
                      <option key={p.id} value={p.id}>
                        {p.identifier} — {p.name}
                      </option>
                    ))}
                  </NativeSelect>
                </Field>
              )}
              {action.kind === "file" && (
                <>
                  <Field label="Categoria">
                    <NativeSelect name="category" defaultValue="technical_doc">
                      {Object.entries(CATEGORY_LABELS).map(([id, label]) => (
                        <option key={id} value={id}>
                          {label}
                        </option>
                      ))}
                    </NativeSelect>
                  </Field>
                  <Field label="Conteúdo sintético">
                    <textarea name="content" className="field" />
                  </Field>
                </>
              )}
              <Submit />
            </form>
          )
        )}
      </Modal>
    </PageContainer>
  );
}
