"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { ClaimList } from "@/components/evidence/claim-list";
import { TextField } from "@/components/forms/text-field";
import { PageHeader, Section } from "@/components/layout/page-header";
import { CorrectionForm } from "@/components/researcher/correction-form";
import { ReviewStateBadge } from "@/components/status/badges";
import { AwaitingState, ErrorState, LoadingState, StaleBanner } from "@/components/status/states";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import type { ReportDetail } from "@/lib/contracts/provisional";
import { useProjectContext, useReport, useSubmitReview } from "@/lib/queries";

const MIN_JUSTIFICATION = 3;

function VersionNav({ detail, reportId }: { detail: ReportDetail; reportId: string }) {
  return (
    <nav aria-label="Versões" className="flex flex-wrap gap-1 text-sm">
      {detail.history.map((h) => (
        <Link
          key={h.id}
          href={`/pesquisador/relatorios/${reportId}?v=${h.version}`}
          aria-current={h.version === detail.version.version ? "page" : undefined}
          className="rounded-md border px-2 py-0.5 hover:bg-muted aria-[current=page]:bg-muted aria-[current=page]:font-medium"
        >
          v{h.version}
        </Link>
      ))}
    </nav>
  );
}

function ApprovalPanel({ detail, authorName }: { detail: ReportDetail; authorName: string }) {
  const [justification, setJustification] = useState("");
  const review = useSubmitReview();
  const { version } = detail;
  const alreadyApproved = detail.reviews.some((r) => r.role === "researcher" && r.decision === "approve");

  if (alreadyApproved) {
    return (
      <AwaitingState title={`Você aprovou a v${version.version}`}>
        Agora o relatório aguarda a consolidação pelo gerente. Uma nova versão exigirá nova aprovação.
      </AwaitingState>
    );
  }

  return (
    <div className="space-y-2 rounded-lg border p-4">
      <p className="text-sm">
        Atuando como <strong>{authorName}</strong> (demonstração). A aprovação vale apenas para a{" "}
        <strong>v{version.version}</strong> e não é aprovação fiscal.
      </p>
      <TextField label="Comentário da aprovação" value={justification} onChange={setJustification} />
      {review.isError && <ErrorState error={review.error} onRetry={() => review.reset()} />}
      <Button
        disabled={justification.trim().length < MIN_JUSTIFICATION || review.isPending}
        onClick={() =>
          review.mutate({
            reportVersionId: version.id,
            reviewerId: version.author_id,
            role: "researcher",
            decision: "approve",
            justification: justification.trim(),
          })
        }
      >
        {review.isPending ? "Registrando…" : `Aprovar versão v${version.version}`}
      </Button>
    </div>
  );
}

export function ReportReview({ reportId, version }: { reportId: string; version?: number }) {
  const router = useRouter();
  const context = useProjectContext();
  const report = useReport(reportId, version);

  if (report.isError) return <ErrorState error={report.error} onRetry={() => report.refetch()} />;
  if (context.isError) return <ErrorState error={context.error} onRetry={() => context.refetch()} />;
  if (report.isPending || context.isPending) return <LoadingState label="Carregando relatório…" />;

  const detail = report.data;
  const current = detail.version;
  const isLatest = current.version === detail.latest_version;
  const authorName = context.data.people.find((p) => p.id === current.author_id)?.name ?? "pesquisador";

  return (
    <div className="space-y-8">
      <PageHeader
        title={`Relatório de ${authorName} · v${current.version}`}
        subtitle={
          <span className="flex flex-wrap items-center gap-2">
            {context.data.period.label} <ReviewStateBadge state={current.review_state} />
          </span>
        }
        actions={<VersionNav detail={detail} reportId={reportId} />}
      />

      {!isLatest && (
        <Alert>
          <AlertTitle>Você está vendo uma versão antiga (v{current.version})</AlertTitle>
          <AlertDescription>
            A versão atual é a v{detail.latest_version}. Revisões só valem para a versão atual.{" "}
            <Link className="underline" href={`/pesquisador/relatorios/${reportId}`}>
              Ir para a v{detail.latest_version}
            </Link>
          </AlertDescription>
        </Alert>
      )}
      {current.stale && current.stale_reason && <StaleBanner reason={current.stale_reason} />}
      {current.change_summary && (
        <p className="text-sm text-muted-foreground">O que mudou nesta versão: {current.change_summary}</p>
      )}

      {current.gaps.length > 0 && (
        <Section title="Lacunas: o sistema não encontrou a informação">
          <ul className="space-y-2">
            {current.gaps.map((gap) => (
              <li key={gap.id} className="rounded-md border border-amber-300 p-3 text-sm dark:border-amber-800">
                <p className="font-medium">{gap.description}</p>
                <p className="text-muted-foreground">{gap.question}</p>
              </li>
            ))}
          </ul>
        </Section>
      )}

      <Section title="Afirmações e fontes">
        <ClaimList
          claims={current.claims}
          evidence={detail.evidence}
          renderAction={(claim) =>
            isLatest ? (
              <CorrectionForm
                claim={claim}
                reportVersionId={current.id}
                onDone={() => router.replace(`/pesquisador/relatorios/${reportId}`)}
              />
            ) : null
          }
        />
      </Section>

      <Section title="Revisão">
        {isLatest ? (
          <ApprovalPanel detail={detail} authorName={authorName} />
        ) : (
          <p className="text-sm text-muted-foreground">Versões antigas ficam no histórico e não podem ser aprovadas.</p>
        )}
      </Section>
    </div>
  );
}
