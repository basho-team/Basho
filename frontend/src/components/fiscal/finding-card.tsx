"use client";

import { Loader2 } from "lucide-react";
import { SourceList } from "@/components/evidence/source-list";
import { DecisionForm, ReturnPendingForm } from "@/components/fiscal/finding-actions";
import { FindingSignalBadge } from "@/components/status/badges";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";
import type { EvidenceVersion, FiscalDecision, Finding } from "@/lib/contracts/provisional";

const DECISION_LABEL: Record<FiscalDecision["decision"], string> = {
  agree: "Concorda",
  disagree: "Discorda",
  defer: "Adiada",
};

const dateFormat = new Intl.DateTimeFormat("pt-BR", { dateStyle: "short", timeStyle: "short" });

interface FindingCardProps {
  finding: Finding;
  evidence: EvidenceVersion[];
  decisions: FiscalDecision[];
}

/** Separa fatos documentados (fontes), interpretação da IA e decisão humana. */
export function FindingCard({ finding, evidence, decisions }: FindingCardProps) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex flex-wrap items-center gap-2 text-base">
          {finding.object.label}
          <FindingSignalBadge signal={finding.signal} />
          {finding.awaiting_reanalysis && (
            <Badge variant="outline">
              <Loader2 className="animate-spin" aria-hidden /> Aguardando reanálise
            </Badge>
          )}
        </CardTitle>
        <CardDescription>
          {finding.criterion.code}: {finding.criterion.title} · {finding.criterion.reference} · versão{" "}
          {finding.criterion.version}
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4 text-sm">
        <div className="space-y-1">
          <h3 className="font-medium">Fatos documentados</h3>
          <SourceList evidence={evidence} ids={finding.evidence_ids} />
        </div>
        <div className="space-y-1">
          <h3 className="font-medium">Interpretação do sistema (não é decisão)</h3>
          <p>{finding.justification}</p>
          {finding.gaps.length > 0 && (
            <ul className="list-disc pl-5 text-amber-800 dark:text-amber-300">
              {finding.gaps.map((gap) => (
                <li key={gap}>Lacuna: {gap}</li>
              ))}
            </ul>
          )}
          <p className="text-muted-foreground">Próximo passo: {finding.next_step}</p>
        </div>
        <Separator />
        <div className="space-y-2">
          <h3 className="font-medium">Decisão humana</h3>
          {decisions.length === 0 && <p className="text-muted-foreground">Nenhuma decisão registrada.</p>}
          {decisions.map((d) => (
            <p key={d.id}>
              <strong>{DECISION_LABEL[d.decision]}</strong>: {d.note}{" "}
              <span className="text-muted-foreground">({dateFormat.format(new Date(d.created_at))})</span>
            </p>
          ))}
          <div className="grid gap-4 md:grid-cols-2">
            <div className="space-y-2">
              <h4 className="text-xs font-medium tracking-wide text-muted-foreground uppercase">Registrar decisão</h4>
              <DecisionForm findingId={finding.id} />
            </div>
            <div className="space-y-2">
              <h4 className="text-xs font-medium tracking-wide text-muted-foreground uppercase">Devolver pendência</h4>
              <ReturnPendingForm findingId={finding.id} />
            </div>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
