import { Suspense } from "react";
import AuditModule from "@/components/modules/AuditModule";
export default function AuditPage() {
  return (
    <Suspense fallback={<p>Carregando auditoria…</p>}>
      <AuditModule />
    </Suspense>
  );
}
