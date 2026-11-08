import { PageHeader } from "@/components/layout/page-header";
import { PendingInbox } from "@/components/pending/pending-inbox";

export default function PendenciasPesquisadorPage() {
  return (
    <div className="space-y-6">
      <PageHeader title="Pendências para o pesquisador" subtitle="Perguntas do sistema e pedidos de outros papéis, com o estado atual." />
      <PendingInbox role="researcher" personId="p-ana" />
    </div>
  );
}
