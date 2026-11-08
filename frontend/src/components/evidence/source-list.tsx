import { FileText, GitPullRequest, MessageSquareQuote, NotebookPen } from "lucide-react";
import { SyntheticBadge } from "@/components/status/badges";
import type { EvidenceVersion } from "@/lib/contracts/provisional";

const SOURCE_ICON = {
  github: GitPullRequest,
  upload: FileText,
  notion: NotebookPen,
  researcher_statement: MessageSquareQuote,
} as const;

const SOURCE_LABEL = {
  github: "GitHub",
  upload: "Upload",
  notion: "Notion",
  researcher_statement: "Declaração",
} as const;

const dateFormat = new Intl.DateTimeFormat("pt-BR", { dateStyle: "short", timeStyle: "short" });

export function SourceItem({ evidence }: { evidence: EvidenceVersion }) {
  const Icon = SOURCE_ICON[evidence.source];
  return (
    <li className="flex gap-3 rounded-md border p-3 text-sm">
      <Icon className="mt-0.5 size-4 shrink-0 text-muted-foreground" aria-hidden />
      <div className="min-w-0 flex-1 space-y-1">
        <div className="flex flex-wrap items-center gap-2">
          <span className="font-medium">{evidence.title}</span>
          {evidence.is_synthetic && <SyntheticBadge />}
        </div>
        {evidence.excerpt && <blockquote className="border-l-2 pl-2 text-muted-foreground">{evidence.excerpt}</blockquote>}
        <p className="font-mono text-xs break-all text-muted-foreground">
          {SOURCE_LABEL[evidence.source]} · {evidence.external_id} · rev {evidence.revision}
          {evidence.locator && ` · ${evidence.locator}`} · {evidence.content_hash.slice(0, 17)} · capturado{" "}
          {dateFormat.format(new Date(evidence.captured_at))}
        </p>
      </div>
    </li>
  );
}

export function SourceList({ evidence, ids }: { evidence: EvidenceVersion[]; ids: string[] }) {
  const cited = evidence.filter((e) => ids.includes(e.id));
  if (cited.length === 0) {
    return <p className="text-sm text-muted-foreground">Sem fonte vinculada.</p>;
  }
  return (
    <ul className="space-y-2">
      {cited.map((e) => (
        <SourceItem key={e.id} evidence={e} />
      ))}
    </ul>
  );
}
