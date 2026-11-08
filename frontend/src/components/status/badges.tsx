import { Badge } from "@/components/ui/badge";
import type { ClaimStatus, FindingSignal, ReviewState, RunStatus } from "@/lib/contracts/provisional";

type Tone = "ok" | "warn" | "danger" | "info" | "muted";

const TONE_CLASS: Record<Tone, string> = {
  ok: "bg-emerald-100 text-emerald-900 dark:bg-emerald-950 dark:text-emerald-200",
  warn: "bg-amber-100 text-amber-900 dark:bg-amber-950 dark:text-amber-200",
  danger: "bg-red-100 text-red-900 dark:bg-red-950 dark:text-red-200",
  info: "bg-sky-100 text-sky-900 dark:bg-sky-950 dark:text-sky-200",
  muted: "bg-muted text-muted-foreground",
};

function ToneBadge({ tone, children }: { tone: Tone; children: React.ReactNode }) {
  return <Badge className={TONE_CLASS[tone]}>{children}</Badge>;
}

const REVIEW: Record<ReviewState, [string, Tone]> = {
  draft: ["Rascunho", "muted"],
  awaiting_researcher: ["Aguardando pesquisador", "warn"],
  awaiting_manager: ["Aprovado pelo pesquisador", "info"],
  available_to_fiscal: ["Disponível ao fiscal", "ok"],
  text_approved: ["Texto aprovado por pesquisador e gerente", "ok"],
  superseded: ["Versão substituída", "muted"],
};

const CLAIM: Record<ClaimStatus, [string, Tone]> = {
  supported: ["Sustentada por fonte", "ok"],
  pending: ["Pendente", "warn"],
  disputed: ["Contestada", "danger"],
};

const SIGNAL: Record<FindingSignal, [string, Tone]> = {
  supported_by_evidence: ["Sustentado pelas evidências", "ok"],
  insufficient_information: ["Informação insuficiente", "warn"],
  possible_incompatibility: ["Possível incompatibilidade", "danger"],
  fiscal_judgment_required: ["Exige interpretação fiscal", "info"],
};

const RUN: Record<RunStatus, [string, Tone]> = {
  queued: ["Na fila", "muted"],
  running: ["Processando", "info"],
  awaiting_input: ["Aguardando resposta", "warn"],
  completed: ["Concluído", "ok"],
  failed: ["Falhou", "danger"],
};

export function ReviewStateBadge({ state }: { state: ReviewState }) {
  const [label, tone] = REVIEW[state];
  return <ToneBadge tone={tone}>{label}</ToneBadge>;
}

export function ClaimStatusBadge({ status }: { status: ClaimStatus }) {
  const [label, tone] = CLAIM[status];
  return <ToneBadge tone={tone}>{label}</ToneBadge>;
}

export function FindingSignalBadge({ signal }: { signal: FindingSignal }) {
  const [label, tone] = SIGNAL[signal];
  return <ToneBadge tone={tone}>{label}</ToneBadge>;
}

export function RunStatusBadge({ status }: { status: RunStatus }) {
  const [label, tone] = RUN[status];
  return <ToneBadge tone={tone}>{label}</ToneBadge>;
}

export function SyntheticBadge() {
  return (
    <Badge variant="outline" title="Dado fictício criado para a demonstração">
      Sintético
    </Badge>
  );
}
