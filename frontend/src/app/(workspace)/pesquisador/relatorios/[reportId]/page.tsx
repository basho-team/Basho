import { Suspense } from "react";
import { ReportReview } from "@/components/researcher/report-review";
import { LoadingState } from "@/components/status/states";

type Props = PageProps<"/pesquisador/relatorios/[reportId]">;

function parseVersion(raw: string | string[] | undefined): number | undefined {
  const value = Number(Array.isArray(raw) ? raw[0] : raw);
  return Number.isInteger(value) && value > 0 ? value : undefined;
}

async function ReportRoute({ params, searchParams }: Props) {
  const { reportId } = await params;
  const { v } = await searchParams;
  return <ReportReview reportId={reportId} version={parseVersion(v)} />;
}

export default function RelatorioPage(props: Props) {
  return (
    <Suspense fallback={<LoadingState label="Carregando relatório…" />}>
      <ReportRoute {...props} />
    </Suspense>
  );
}
