import Link from "next/link";
import { Card, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";

const ROLES = [
  {
    href: "/pesquisador",
    title: "Pesquisador",
    text: "Recebe o relatório do período pronto, com fontes e lacunas. Corrige, responde e aprova a versão exata.",
  },
  {
    href: "/gerente",
    title: "Gerente de projetos",
    text: "Vê a consolidação, o que está revisado ou pendente, pede esclarecimentos e encaminha ao fiscal.",
  },
  {
    href: "/fiscal",
    title: "Fiscal",
    text: "Examina pacote, despesas e sinalizações com critério e fonte, registra sua decisão e devolve pendências.",
  },
] as const;

export default function Home() {
  return (
    <div className="space-y-8">
      <section className="space-y-2">
        <h1 className="text-3xl font-semibold tracking-tight">Basho</h1>
        <p className="max-w-2xl text-muted-foreground">
          Operação de projetos de P&amp;D com a conformidade da Lei do Bem embutida no fluxo. O sistema prepara os
          registros; as pessoas revisam, decidem e respondem.
        </p>
        <p className="max-w-2xl text-sm text-muted-foreground">
          Cenário sintético: Lumen Sensores (fictícia), projeto “Calibração adaptativa de sensores ópticos”, período
          outubro/2026, dois pesquisadores. Inclui um experimento sem resultado positivo, horas não informadas e uma
          nota fiscal mista sem critério de alocação. Sinalizações não são garantia de benefício fiscal.
        </p>
      </section>
      <section className="grid gap-4 sm:grid-cols-3" aria-label="Escolha um papel">
        {ROLES.map((role) => (
          <Link key={role.href} href={role.href} className="rounded-xl focus-visible:ring-3 focus-visible:ring-ring/50">
            <Card className="h-full transition-colors hover:bg-muted/50">
              <CardHeader>
                <CardTitle>{role.title}</CardTitle>
                <CardDescription>{role.text}</CardDescription>
              </CardHeader>
            </Card>
          </Link>
        ))}
      </section>
    </div>
  );
}
