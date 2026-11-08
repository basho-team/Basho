import { FlaskConical } from "lucide-react";
import { publicEnv } from "@/lib/env";

/** Sempre visível: deixa claro que a troca de papel não é autenticação e os dados são fictícios. */
export function DemoBanner() {
  const isMock = publicEnv.NEXT_PUBLIC_DATA_SOURCE === "mock";
  return (
    <div
      role="note"
      className="flex items-center justify-center gap-2 border-b border-primary/20 bg-accent px-4 py-1.5 text-center text-xs font-medium text-accent-foreground"
    >
      <FlaskConical className="size-3.5 shrink-0" aria-hidden />
      <span>
        Modo demonstração: troca de papel sem autenticação.{" "}
        {isMock
          ? "Dados sintéticos e backend simulado no navegador (recarregar reinicia o cenário)."
          : "Fonte de dados: API do backend."}
      </span>
    </div>
  );
}
