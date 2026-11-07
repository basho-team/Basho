import { ClaimStatusBadge } from "@/components/status/badges";
import { SourceList } from "@/components/evidence/source-list";
import { Badge } from "@/components/ui/badge";
import type { Claim, EvidenceVersion } from "@/lib/contracts/provisional";

const SECTION_LABEL: Record<Claim["section"], string> = {
  activity: "Atividade",
  experiment: "Experimento",
  result: "Resultado",
  hours: "Horas",
  next_steps: "Próximos passos",
};

interface ClaimListProps {
  claims: Claim[];
  evidence: EvidenceVersion[];
  renderAction?: (claim: Claim) => React.ReactNode;
}

/** Afirmação + status + fontes. Lacuna aparece como pendente, nunca preenchida pela UI. */
export function ClaimList({ claims, evidence, renderAction }: ClaimListProps) {
  return (
    <ol className="space-y-4">
      {claims.map((claim) => (
        <li key={claim.id} className="space-y-2 rounded-lg border p-4">
          <div className="flex flex-wrap items-center gap-2 text-xs">
            <span className="font-medium tracking-wide text-muted-foreground uppercase">
              {SECTION_LABEL[claim.section]}
            </span>
            <ClaimStatusBadge status={claim.status} />
            {claim.corrected_by_human && <Badge variant="outline">Corrigido por pessoa</Badge>}
          </div>
          <p className={claim.status === "pending" ? "text-muted-foreground italic" : undefined}>{claim.text}</p>
          <p className="text-xs text-muted-foreground">Por quê: {claim.justification}</p>
          <SourceList evidence={evidence} ids={claim.evidence_ids} />
          {renderAction?.(claim)}
        </li>
      ))}
    </ol>
  );
}
