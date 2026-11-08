"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useQueryClient } from "@tanstack/react-query";
import { useSyncExternalStore, type ReactNode } from "react";

import { Badge, ErrorBox, Loading } from "@/components/basho/ui";
import { useDemoContext } from "@/components/basho/hooks";
import { PROHIBITED_NOTE } from "@/lib/labels";
import { PERSONA_COOKIE, parsePersona, serializePersona, type Persona, type Role } from "@/lib/persona";
import type { DemoContext } from "@/lib/types";

const NAV: { href: string; label: string; role: Role }[] = [
  { href: "/pesquisador", label: "Pesquisador", role: "researcher" },
  { href: "/gerente", label: "Gerente", role: "manager" },
  { href: "/fiscal", label: "Fiscal", role: "fiscal" },
];

const listeners = new Set<() => void>();

function personaCookie(): string {
  const raw = document.cookie.split("; ").find((c) => c.startsWith(`${PERSONA_COOKIE}=`));
  return raw?.split("=")[1] ?? "";
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export function usePersona(): [Persona | null, (p: Persona) => void] {
  const raw = useSyncExternalStore(subscribe, personaCookie, () => "");
  const queryClient = useQueryClient();
  const update = (p: Persona) => {
    document.cookie = `${PERSONA_COOKIE}=${serializePersona(p)}; path=/; SameSite=Strict`;
    listeners.forEach((l) => l());
    void queryClient.invalidateQueries();
  };
  return [parsePersona(raw), update];
}

function PersonaSwitcher({ ctx, persona, onChange }: {
  ctx: DemoContext; persona: Persona | null; onChange: (p: Persona) => void;
}) {
  const router = useRouter();
  return (
    <label className="flex items-center gap-2 text-sm">
      <span className="text-zinc-600">Atuando como</span>
      <select
        className="rounded border border-zinc-300 bg-white px-2 py-1 text-sm"
        value={persona?.userId ?? ""}
        onChange={(e) => {
          const person = ctx.people.find((p) => p.id === e.target.value);
          if (!person) return;
          onChange({ userId: person.id, role: person.role });
          const target = NAV.find((n) => n.role === person.role);
          if (target) router.push(target.href);
        }}
      >
        <option value="" disabled>escolha…</option>
        {ctx.people.map((p) => (
          <option key={p.id} value={p.id}>{p.name} — {NAV.find((n) => n.role === p.role)?.label}</option>
        ))}
      </select>
    </label>
  );
}

export function Shell({ children }: { children: (ctx: DemoContext, persona: Persona | null) => ReactNode }) {
  const context = useDemoContext();
  const [persona, setPersona] = usePersona();
  const pathname = usePathname();
  return (
    <div className="min-h-full bg-zinc-50">
      <div className="bg-amber-100 px-4 py-1.5 text-center text-xs text-amber-900">
        Demonstração com <strong>dados sintéticos</strong>. A troca de papel não é autenticação. {PROHIBITED_NOTE}
      </div>
      <header className="border-b border-zinc-200 bg-white">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-3 px-4 py-3">
          <Link href="/" className="text-lg font-bold tracking-tight">Basho</Link>
          <nav className="flex gap-1 text-sm">
            {NAV.map((n) => (
              <Link key={n.href} href={n.href}
                className={`rounded px-2 py-1 ${pathname.startsWith(n.href) ? "bg-zinc-900 text-white" : "text-zinc-700 hover:bg-zinc-100"}`}>
                {n.label}
              </Link>
            ))}
          </nav>
          {context.data && <PersonaSwitcher ctx={context.data} persona={persona} onChange={setPersona} />}
        </div>
      </header>
      <main className="mx-auto w-full max-w-6xl px-4 py-6">
        {context.isPending && <Loading label="Conectando à API do Basho…" />}
        {context.isError && <ErrorBox error={context.error} onRetry={() => void context.refetch()} />}
        {context.data && (
          <>
            <div className="mb-4 flex flex-wrap items-center gap-2 text-sm text-zinc-600">
              <span className="font-medium text-zinc-900">{context.data.project_name}</span>
              <Badge>período {context.data.period.start} a {context.data.period.end}</Badge>
              <Badge tone={context.data.ai_maker_available ? "ok" : "warn"}>
                IA (Maker/Checker): {context.data.ai_maker_available ? "disponível" : "indisponível nesta demo"}
              </Badge>
            </div>
            {children(context.data, persona)}
          </>
        )}
      </main>
    </div>
  );
}

export function RequirePersona({ persona, role, ctx, children }: {
  persona: Persona | null; role: Role; ctx: DemoContext; children: ReactNode;
}) {
  if (persona?.role === role) return <>{children}</>;
  const options = ctx.people.filter((p) => p.role === role).map((p) => p.name).join(" ou ");
  return (
    <p className="rounded border border-sky-200 bg-sky-50 p-3 text-sm text-sky-900">
      Escolha no topo uma persona com este papel ({options}) para agir nesta tela.
    </p>
  );
}
