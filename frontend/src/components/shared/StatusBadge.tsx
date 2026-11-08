import { Badge } from "@/components/ui/badge";

const STATUS_MAP: Record<
  string,
  {
    label: string;
    variant:
      | "default"
      | "secondary"
      | "destructive"
      | "outline"
      | "success"
      | "warning"
      | "info";
  }
> = {
  // RunStatus
  waiting: { label: "Aguardando", variant: "secondary" },
  running: { label: "Em execução", variant: "info" },
  completed: { label: "Concluído", variant: "success" },
  failed: { label: "Falhou", variant: "destructive" },
  awaiting_approval: { label: "Aguardando aprovação", variant: "warning" },
  blocked_by_policy: {
    label: "Bloqueado por política",
    variant: "destructive",
  },
  // ApprovalStatus
  pending: { label: "Pendente", variant: "warning" },
  approved: { label: "Aprovado", variant: "success" },
  rejected: { label: "Rejeitado", variant: "destructive" },
  needs_revision: { label: "Requer revisão", variant: "info" },
  // ActivityStatus
  todo: { label: "A Fazer", variant: "secondary" },
  in_progress: { label: "Em Andamento", variant: "info" },
  review: { label: "Revisão", variant: "warning" },
  done: { label: "Concluído", variant: "success" },
  blocked: { label: "Bloqueado", variant: "destructive" },
  // DocumentStatus
  present: { label: "Presente", variant: "success" },
  absent: { label: "Ausente", variant: "destructive" },
  draft: { label: "Rascunho", variant: "secondary" },
  pending_review: { label: "Aguardando revisão", variant: "warning" },
  validated: { label: "Validado", variant: "success" },
  // PermissionLevel
  automatic: { label: "Automático", variant: "success" },
  requires_approval: { label: "Exige aprovação", variant: "warning" },
  // ProjectStatus
  planning: { label: "Planejamento", variant: "secondary" },
  active: { label: "Ativo", variant: "success" },
  on_hold: { label: "Suspenso", variant: "warning" },
  cancelled: { label: "Cancelado", variant: "destructive" },
  // EvidenceStatus
  supported: { label: "Suportada", variant: "success" },
  disputed: { label: "Contestada", variant: "destructive" },
};

export function StatusBadge({
  status,
  label,
}: {
  status: string;
  label?: string;
}) {
  const config = STATUS_MAP[status] ?? {
    label: status,
    variant: "outline" as const,
  };
  return <Badge variant={config.variant}>{label ?? config.label}</Badge>;
}
