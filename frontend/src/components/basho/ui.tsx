import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

export function Card({ title, children, className, actions }: {
  title?: ReactNode; children: ReactNode; className?: string; actions?: ReactNode;
}) {
  return (
    <section className={cn("rounded-lg border border-zinc-200 bg-white p-4 shadow-sm", className)}>
      {(title || actions) && (
        <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
          {title && <h2 className="text-base font-semibold text-zinc-900">{title}</h2>}
          {actions}
        </div>
      )}
      {children}
    </section>
  );
}

const TONES = {
  neutral: "bg-zinc-100 text-zinc-700 border-zinc-200",
  ok: "bg-emerald-50 text-emerald-800 border-emerald-200",
  warn: "bg-amber-50 text-amber-900 border-amber-200",
  bad: "bg-rose-50 text-rose-800 border-rose-200",
  info: "bg-sky-50 text-sky-800 border-sky-200",
} as const;
export type Tone = keyof typeof TONES;

export function Badge({ tone = "neutral", children }: { tone?: Tone; children: ReactNode }) {
  return (
    <span className={cn("inline-flex items-center rounded border px-1.5 py-0.5 text-xs font-medium", TONES[tone])}>
      {children}
    </span>
  );
}

export function Loading({ label = "Carregando…" }: { label?: string }) {
  return <p className="animate-pulse text-sm text-zinc-500" role="status">{label}</p>;
}

export function Empty({ children }: { children: ReactNode }) {
  return <p className="rounded border border-dashed border-zinc-300 p-3 text-sm text-zinc-500">{children}</p>;
}

export function ErrorBox({ error, onRetry }: { error: unknown; onRetry?: () => void }) {
  const message = error instanceof Error ? error.message : "Erro inesperado";
  return (
    <div role="alert" className="rounded border border-rose-200 bg-rose-50 p-3 text-sm text-rose-800">
      <p>{message}</p>
      {onRetry && (
        <button type="button" onClick={onRetry} className="mt-2 underline">Tentar novamente</button>
      )}
    </div>
  );
}

export function Mono({ children }: { children: ReactNode }) {
  return <code className="rounded bg-zinc-100 px-1 font-mono text-xs text-zinc-700">{children}</code>;
}

export const inputClass =
  "w-full rounded border border-zinc-300 bg-white px-2 py-1.5 text-sm focus:border-sky-500 focus:outline-none";
export const buttonClass =
  "inline-flex items-center justify-center rounded bg-zinc-900 px-3 py-1.5 text-sm font-medium text-white hover:bg-zinc-700 disabled:cursor-not-allowed disabled:opacity-50";
export const secondaryButtonClass =
  "inline-flex items-center justify-center rounded border border-zinc-300 bg-white px-3 py-1.5 text-sm font-medium text-zinc-800 hover:bg-zinc-50 disabled:opacity-50";
