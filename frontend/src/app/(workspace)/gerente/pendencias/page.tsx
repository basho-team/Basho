import { PageHeader } from "@/components/layout/page-header";
import { PendingInbox } from "@/components/pending/pending-inbox";

export default function PendenciasGerentePage() {
  return (
    <div className="space-y-6">
      <PageHeader title="Pendências para o gerente" subtitle="Perguntas do sistema e pedidos de outros papéis, com o estado atual." />
      <PendingInbox role="manager" personId="p-marina" />
    </div>
  );
}
