"use client";

import { usePathname } from "next/navigation";
import { Suspense } from "react";
import { ThemeToggle } from "@/components/theme/theme-toggle";
import { activeItem } from "./nav";

function Context({ pathname }: { pathname: string | null }) {
  const item = activeItem(pathname);
  return (
    <p className="min-w-0 truncate text-sm text-muted-foreground">
      {item?.person ? (
        <>
          Visão de <span className="font-medium text-foreground">{item.label}</span> · {item.person}
        </>
      ) : (
        "Visão geral da demonstração"
      )}
    </p>
  );
}

function ActiveContext() {
  return <Context pathname={usePathname()} />;
}

export function TopBar() {
  return (
    <div className="sticky top-0 z-10 flex items-center justify-between gap-4 border-b bg-background/85 px-4 py-2.5 backdrop-blur md:px-8">
      <Suspense fallback={<Context pathname={null} />}>
        <ActiveContext />
      </Suspense>
      <ThemeToggle />
    </div>
  );
}
