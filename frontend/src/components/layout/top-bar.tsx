"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { useQueryClient } from "@tanstack/react-query";
import { LogOut } from "lucide-react";
import { useDemoUser } from "@/components/auth/session-provider";
import { ThemeToggle } from "@/components/theme/theme-toggle";
import { ROLE_LABELS } from "@/lib/auth/shared";

export function TopBar() {
  const user = useDemoUser();
  const router = useRouter();
  const queryClient = useQueryClient();
  const [error, setError] = useState(false);
  const [pending, setPending] = useState(false);
  async function logout() {
    setPending(true);
    setError(false);
    try {
      const response = await fetch("/api/auth/logout", { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}" });
      if (!response.ok) { setError(true); return; }
      queryClient.clear();
      router.replace("/login");
      router.refresh();
    } catch { setError(true); } finally { setPending(false); }
  }
  return (
    <header className="sticky top-0 z-10 flex flex-wrap items-center justify-between gap-3 border-b bg-background/95 px-4 py-3 backdrop-blur md:px-8">
      <div><p className="text-sm font-medium">{user.name}</p><p className="text-xs text-muted-foreground">{ROLE_LABELS[user.role]} · Lumen Sensores</p></div>
      <div className="flex items-center gap-3">
        <ThemeToggle />
        <button type="button" onClick={logout} disabled={pending}
          className="inline-flex items-center gap-1.5 rounded-lg border px-3 py-1.5 text-xs hover:bg-muted focus-visible:ring-3 focus-visible:ring-ring/40">
          <LogOut className="size-3.5" aria-hidden />{pending ? "Saindo…" : "Sair"}
        </button>
      </div>
      {error && <p role="alert" className="w-full text-sm text-destructive">Não foi possível sair. Tente novamente.</p>}
    </header>
  );
}
