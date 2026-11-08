import { Suspense } from "react";
import DocumentsModule from "@/components/modules/DocumentsModule";
export default function DocumentsPage() {
  return (
    <Suspense fallback={<p>Carregando documentos…</p>}>
      <DocumentsModule />
    </Suspense>
  );
}
