"use client";

import { Monitor, Moon, Sun } from "lucide-react";
import { useLayoutEffect } from "react";
import { cn } from "cn";
import { applyTheme, readPreference, setPreference, useThemePreference, type ThemePreference } from "@/lib/theme";

const OPTIONS: ReadonlyArray<{ value: ThemePreference; label: string; icon: typeof Sun }> = [
  { value: "light", label: "Tema claro", icon: Sun },
  { value: "system", label: "Tema do sistema", icon: Monitor },
  { value: "dark", label: "Tema escuro", icon: Moon },
];

export function ThemeToggle({ className }: { className?: string }) {
  const preference = useThemePreference();

  // Em desenvolvimento o StrictMode remonta e o React limpa a classe do <html>: reaplica antes
  // da pintura. Em produção é inofensivo (o script do <head> já aplicou).
  useLayoutEffect(() => {
    applyTheme(readPreference());
  }, []);

  return (
    <div
      role="group"
      aria-label="Aparência"
      className={cn("inline-flex items-center gap-0.5 rounded-full bg-muted p-0.5 ring-1 ring-border", className)}
    >
      {OPTIONS.map(({ value, label, icon: Icon }) => {
        const selected = preference === value;
        return (
          <button
            key={value}
            type="button"
            title={label}
            aria-label={label}
            aria-pressed={selected}
            onClick={() => setPreference(value)}
            className={cn(
              "inline-flex size-7 items-center justify-center rounded-full text-muted-foreground transition-colors outline-none hover:text-foreground focus-visible:ring-3 focus-visible:ring-ring/50",
              selected && "bg-card text-foreground shadow-sm ring-1 ring-border",
            )}
          >
            <Icon className="size-3.5" aria-hidden />
          </button>
        );
      })}
    </div>
  );
}
