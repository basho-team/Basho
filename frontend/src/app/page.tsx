"use client";

import Link from "next/link";

import { Shell } from "@/components/basho/shell";
import { Card } from "@/components/basho/ui";

const STEPS = [
  ["Pesquisador", "/pesquisador", "Registra atividade e evidências, monta o relatório, recebe verificações, corrige (nova versão) e confirma a versão exata."],
  ["Gerente", "/gerente", "Vê relatórios e estados de revisão, a consolidação do período com negativos preservados e pede esclarecimentos."],
  ["Fiscal", "/fiscal", "Consulta o dossiê: cada item com evidências do ledger (hash e localizador) e lacunas explícitas, para análise humana."],
] as const;

export default function Home() {
  return (
    <Shell>
      {() => (
        <div className="space-y-4">
          <h1 className="text-2xl font-semibold">Jornada da demonstração</h1>
          <p className="text-sm text-zinc-600">Escolha uma persona no topo (Ana, Bia, Carla ou Davi) e siga as etapas.</p>
          <div className="grid gap-4 md:grid-cols-3">
            {STEPS.map(([title, href, text], i) => (
              <Card key={href} title={`${i + 1}. ${title}`}>
                <p className="mb-3 text-sm text-zinc-700">{text}</p>
                <Link href={href} className="text-sm font-medium underline">Abrir {title.toLowerCase()}</Link>
              </Card>
            ))}
          </div>
        </div>
      )}
    </Shell>
  );
}
