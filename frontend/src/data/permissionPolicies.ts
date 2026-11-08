import type { PermissionPolicy } from "@/types";

export const seedPermissionPolicies: PermissionPolicy[] = [
  // Google Drive
  { id: "pp-gd-01", provider: "google_drive", operation: "read_files", label: "Ler arquivos", description: "Permitir leitura de documentos no Drive", level: "automatic", category: "read" },
  { id: "pp-gd-02", provider: "google_drive", operation: "create_documents", label: "Criar documentos", description: "Criar novos documentos derivados", level: "automatic", category: "write_internal" },
  { id: "pp-gd-03", provider: "google_drive", operation: "create_folders", label: "Criar pastas", description: "Criar novas pastas de organização", level: "automatic", category: "write_internal" },
  { id: "pp-gd-04", provider: "google_drive", operation: "copy_documents", label: "Copiar documentos", description: "Criar cópias de trabalho de documentos", level: "automatic", category: "write_internal" },
  { id: "pp-gd-05", provider: "google_drive", operation: "move_derived", label: "Mover arquivos derivados", description: "Reorganizar arquivos derivados entre pastas", level: "automatic", category: "write_internal" },
  { id: "pp-gd-06", provider: "google_drive", operation: "rename_derived", label: "Renomear documentos derivados", description: "Renomear arquivos gerados pelo sistema", level: "automatic", category: "write_internal" },
  { id: "pp-gd-07", provider: "google_drive", operation: "modify_originals", label: "Modificar documentos originais", description: "Editar contratos, notas fiscais e originais", level: "blocked", category: "formal" },
  { id: "pp-gd-08", provider: "google_drive", operation: "delete_files", label: "Excluir arquivos", description: "Remover arquivos do Drive", level: "blocked", category: "formal" },

  // Notion
  { id: "pp-nt-01", provider: "notion", operation: "read_activities", label: "Consultar atividades", description: "Ler atividades da base do Notion", level: "automatic", category: "read" },
  { id: "pp-nt-02", provider: "notion", operation: "create_tasks", label: "Criar tarefas", description: "Criar novas tarefas na base vinculada", level: "automatic", category: "external" },
  { id: "pp-nt-03", provider: "notion", operation: "update_descriptions", label: "Atualizar descrições", description: "Editar a descrição de tarefas existentes", level: "automatic", category: "external" },
  { id: "pp-nt-04", provider: "notion", operation: "update_priorities", label: "Atualizar prioridades", description: "Alterar a prioridade de tarefas", level: "requires_approval", category: "external" },
  { id: "pp-nt-05", provider: "notion", operation: "change_assignees", label: "Alterar responsáveis", description: "Reatribuir tarefas para outras pessoas", level: "requires_approval", category: "external" },
  { id: "pp-nt-06", provider: "notion", operation: "change_status", label: "Alterar status", description: "Mover tarefas entre colunas do Kanban", level: "automatic", category: "external" },
  { id: "pp-nt-07", provider: "notion", operation: "complete_activities", label: "Concluir atividades", description: "Marcar tarefas como concluídas", level: "requires_approval", category: "external" },
  { id: "pp-nt-08", provider: "notion", operation: "add_evidence", label: "Adicionar evidências", description: "Vincular evidências a atividades", level: "automatic", category: "external" },

  // GitHub
  { id: "pp-gh-01", provider: "github", operation: "read_events", label: "Consultar eventos", description: "Ler commits, PRs, issues e releases", level: "automatic", category: "read" },
  { id: "pp-gh-02", provider: "github", operation: "monitor_repos", label: "Monitorar repositórios", description: "Acompanhar repositórios configurados", level: "automatic", category: "read" },
  { id: "pp-gh-03", provider: "github", operation: "link_commits", label: "Relacionar commits a atividades", description: "Associar commits a atividades de P&D", level: "automatic", category: "write_internal" },
  { id: "pp-gh-04", provider: "github", operation: "create_evidence_records", label: "Criar registros de evidência", description: "Gerar registros de evidência técnica", level: "automatic", category: "write_internal" },
  { id: "pp-gh-05", provider: "github", operation: "modify_repos", label: "Alterar conteúdo de repositórios", description: "Modificar código, issues ou configurações", level: "blocked", category: "formal" },
];
