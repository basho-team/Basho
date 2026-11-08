"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Suspense } from "react";
import { cn } from "cn";
import { BashoLogo } from "@/components/brand/logo";
import { useDemoUser } from "@/components/auth/session-provider";
import { NAV_ITEMS, isActive } from "./nav";

function SidebarView({ pathname }: { pathname: string | null }) {
  const user = useDemoUser();
  return (
    <aside className="bg-basho-texture text-sidebar-foreground md:sticky md:top-0 md:flex md:h-dvh md:w-64 md:shrink-0 md:flex-col md:border-r md:border-sidebar-border">
      <div className="px-4 pt-3 pb-2 md:px-6 md:pt-7 md:pb-8">
        <Link
          href="/"
          aria-label="Basho, ir ao início"
          className="inline-flex rounded-md text-sidebar-foreground outline-none focus-visible:ring-3 focus-visible:ring-sidebar-ring"
        >
          <BashoLogo />
        </Link>
      </div>
      <nav
        aria-label="Papéis"
        className="flex gap-1 overflow-x-auto px-3 pb-3 md:flex-1 md:flex-col md:gap-1.5 md:overflow-visible md:px-4 md:pb-0"
      >
        {NAV_ITEMS.filter(item => !item.role || item.role === user.role).map((item) => {
          const active = isActive(item, pathname);
          return (
            <Link
              key={item.href}
              href={item.href}
              aria-current={active ? "page" : undefined}
              className={cn(
                "flex shrink-0 items-center gap-3 rounded-lg px-3 py-2 text-sm outline-none transition-colors focus-visible:ring-3 focus-visible:ring-sidebar-ring md:py-2.5",
                active
                  ? "bg-sidebar-primary font-medium text-sidebar-primary-foreground shadow-sm"
                  : "text-sidebar-foreground/90 hover:bg-sidebar-accent hover:text-sidebar-accent-foreground",
              )}
            >
              <item.icon className="size-4 shrink-0" aria-hidden />
              <span className="flex flex-col leading-tight">
                {item.label}

              </span>
            </Link>
          );
        })}
      </nav>
      <p className="hidden px-6 py-5 text-xs leading-relaxed text-sidebar-foreground/70 md:block">
        Apoio à análise: o sistema prepara registros e sinalizações. Não decide enquadramento nem garante benefício
        fiscal.
      </p>
    </aside>
  );
}

function ActiveSidebar() {
  return <SidebarView pathname={usePathname()} />;
}

export function AppSidebar() {
  return (
    <Suspense fallback={<SidebarView pathname={null} />}>
      <ActiveSidebar />
    </Suspense>
  );
}
