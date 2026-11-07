import { publicEnv } from "@/lib/env";

/** Sempre visível: deixa claro que a troca de papel não é autenticação e os dados são fictícios. */
export function DemoBanner() {
  const isMock = publicEnv.NEXT_PUBLIC_DATA_SOURCE === "mock";
  return (
    <div
      role="note"
      className="bg-amber-100 px-4 py-1.5 text-center text-xs font-medium text-amber-950 dark:bg-amber-950 dark:text-amber-100"
    >
      Modo demonstração: troca de papel sem autenticação.{" "}
      {isMock
        ? "Dados sintéticos e backend simulado no navegador (recarregar reinicia o cenário)."
        : "Fonte de dados: API do backend."}
    </div>
  );
}
