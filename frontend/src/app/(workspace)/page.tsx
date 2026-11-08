"use client";

import { ArrowRight, FlaskConical, LayoutDashboard, Scale } from "lucide-react";
import Link from "next/link";
import { useDemoUser } from "@/components/auth/session-provider";
import { mayVisit, ROLE_HOME } from "@/lib/auth/shared";
import { BashoMark } from "@/components/brand/logo";
import { Card, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";

const ROLES = [
  {
    href: "/pesquisador",
    title: "Pesquisador",
    icon: FlaskConical,
    text: "Recebe o relatório do período pronto, com fontes e lacunas. Corrige, responde e aprova a versão exata.",
  },
  {
    href: "/gerente",
    title: "Gerente de projetos",
    icon: LayoutDashboard,
    text: "Vê a consolidação, o que está revisado ou pendente, pede esclarecimentos e encaminha ao fiscal.",
  },
  {
    href: "/fiscal",
    title: "Fiscal",
    icon: Scale,
    text: "Examina pacote, despesas e sinalizações com critério e fonte, registra sua decisão e devolve pendências.",
  },
] as const;

export default function Home() {
  const user = useDemoUser();
  return (
    <div className="space-y-8">
      <section className="bg-basho-texture relative overflow-hidden rounded-2xl px-6 py-9 text-sidebar-foreground ring-1 ring-sidebar-border md:px-10 md:py-12">
        <BashoMark className="pointer-events-none absolute -right-6 -bottom-8 size-56 text-sidebar-foreground/[0.07] md:size-72" />
        <div className="relative max-w-2xl space-y-3">
          <h1 className="font-serif text-3xl leading-tight font-semibold tracking-tight md:text-4xl">
            P&amp;D documentado, com a Lei do Bem no fluxo.
          </h1>
          <p className="text-sm leading-relaxed text-sidebar-foreground/75 md:text-base">
            O sistema prepara os registros; as pessoas revisam, decidem e respondem. Cada afirmação aponta para a
            evidência que a sustenta.
          </p>
        </div>
      </section>

      <section className="grid gap-4 md:grid-cols-3" aria-label="Seu espaço de trabalho">
        {ROLES.filter(role => role.href === ROLE_HOME[user.role]).map((role) => (
          <Link
            key={role.href}
            href={role.href}
            className="group rounded-xl outline-none focus-visible:ring-3 focus-visible:ring-ring/50"
          >
            <Card className="h-full transition-shadow group-hover:shadow-md group-hover:ring-primary/40">
              <CardHeader className="gap-3">
                <span className="flex size-9 items-center justify-center rounded-lg bg-primary/10 text-primary">
                  <role.icon className="size-4.5" aria-hidden />
                </span>
                <CardTitle className="flex items-center justify-between text-base">
                  {role.title}
                  <ArrowRight
                    className="size-4 text-muted-foreground transition-transform group-hover:translate-x-0.5 group-hover:text-primary"
                    aria-hidden
                  />
                </CardTitle>
                <CardDescription>{role.text}</CardDescription>
              </CardHeader>
            </Card>
          </Link>
        ))}
      </section>

      {mayVisit(user.role, "/integracoes") && (
        <Link href="/integracoes" className="inline-flex rounded-lg border bg-card px-4 py-3 text-sm font-medium text-primary hover:bg-muted">Ver fontes e integrações</Link>
      )}

      <Card>
        <CardHeader>
          <CardTitle>Cenário da demonstração</CardTitle>
          <CardDescription className="max-w-3xl leading-relaxed">
            Lumen Sensores (fictícia), projeto “Calibração adaptativa de sensores ópticos”, período outubro/2026, dois
            pesquisadores. Inclui um experimento sem resultado positivo, horas não informadas e uma nota fiscal mista
            sem critério de alocação. Sinalizações não são garantia de benefício fiscal.
          </CardDescription>
        </CardHeader>
      </Card>
    </div>
  );
}
