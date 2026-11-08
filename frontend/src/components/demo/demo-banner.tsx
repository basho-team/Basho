"use client";

import { FlaskConical } from "lucide-react";
import { publicEnv } from "@/lib/env";

export function DemoBanner() {
  return <div className="flex items-center justify-center gap-2 border-b border-primary/15 bg-primary/10 px-4 py-2 text-center text-xs text-primary">
    <FlaskConical className="size-3.5 shrink-0" aria-hidden />
    <span>{publicEnv.NEXT_PUBLIC_DATA_SOURCE === "mock"
      ? "Demonstração local · contas e dados fictícios · dados compartilhados reiniciam com o servidor."
      : "Demonstração com API · acesso por função · identidade do backend ainda provisória."}</span>
  </div>;
}
