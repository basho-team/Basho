"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Suspense } from "react";
import { cn } from "cn";

const ROLES = [
  { href: "/pesquisador", label: "Pesquisador", person: "Ana Ribeiro / Bruno Costa" },
  { href: "/gerente", label: "Gerente", person: "Marina Duarte" },
  { href: "/fiscal", label: "Fiscal", person: "Rafael Lima" },
] as const;

/** Telas por papel ligadas ao contrato da #5 (a rota define o papel da demonstração). */
const ROLE_PAGES = [
  { href: "/pesquisador/pendencias", label: "Pendências do pesquisador" },
  { href: "/gerente/pendencias", label: "Pendências do gerente" },
  { href: "/gerente/dossie", label: "Dossiê" },
] as const;

function RoleNav({ pathname }: { pathname: string | null }) {
  return (
    <header className="border-b">
      <nav aria-label="Papel" className="mx-auto flex max-w-5xl flex-wrap items-center gap-x-4 gap-y-2 px-4 py-3">
        <Link href="/" className="mr-auto font-semibold tracking-tight">
          Basho
        </Link>
        {ROLES.map((role) => {
          const active = pathname?.startsWith(role.href) ?? false;
          return (
            <Link
              key={role.href}
              href={role.href}
              aria-current={active ? "page" : undefined}
              className={cn(
                "rounded-md px-2 py-1 text-sm transition-colors hover:bg-muted",
                active && "bg-muted font-medium",
              )}
            >
              {role.label}
              <span className="hidden text-muted-foreground lg:inline"> · {role.person}</span>
            </Link>
          );
        })}
      </nav>
      <nav aria-label="Telas" className="mx-auto flex max-w-5xl flex-wrap gap-x-3 gap-y-1 px-4 pb-2 text-xs">
        {ROLE_PAGES.map((page) => (
          <Link
            key={page.href}
            href={page.href}
            aria-current={pathname === page.href ? "page" : undefined}
            className="text-muted-foreground underline-offset-2 hover:underline aria-[current=page]:font-medium aria-[current=page]:text-foreground"
          >
            {page.label}
          </Link>
        ))}
      </nav>
    </header>
  );
}

function ActiveRoleNav() {
  return <RoleNav pathname={usePathname()} />;
}

/** Troca de papel da demonstração. Não é autenticação. */
export function RoleSwitcher() {
  return (
    <Suspense fallback={<RoleNav pathname={null} />}>
      <ActiveRoleNav />
    </Suspense>
  );
}
