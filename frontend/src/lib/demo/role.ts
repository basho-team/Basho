import type { ReviewerRole } from "@/lib/bff/contract";

/**
 * Papel da demonstração definido pela troca de papel (a rota da tela): `/pesquisador` atua
 * como pesquisador e `/gerente` como gerente. Não é autenticação (placeholder até #47).
 * O fiscal não tem papel humano no backend do MVP.
 */
export function roleForPath(pathname: string | null | undefined): ReviewerRole | null {
  if (!pathname) return null;
  if (pathname === "/pesquisador" || pathname.startsWith("/pesquisador/")) return "researcher";
  if (pathname === "/gerente" || pathname.startsWith("/gerente/")) return "manager";
  return null;
}

/** Papel atual no navegador; `null` no servidor ou fora das telas de papel. */
export function currentDemoRole(): ReviewerRole | null {
  return typeof window === "undefined" ? null : roleForPath(window.location.pathname);
}
