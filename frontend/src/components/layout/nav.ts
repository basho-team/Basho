import { FlaskConical, FolderSync, House, LayoutDashboard, Plug, Scale, type LucideIcon } from "lucide-react";
import type { AppRole } from "@/lib/auth/shared";

export interface NavItem {
  href: string;
  label: string;
  role?: AppRole;
  icon: LucideIcon;
  exact?: boolean;
}

export const NAV_ITEMS: readonly NavItem[] = [
  { href: "/", label: "Meu espaço", icon: House, exact: true },
  { href: "/pesquisador", label: "Meus relatórios", role: "researcher", icon: FlaskConical },
  { href: "/gerente", label: "Gestão do projeto", role: "manager", icon: LayoutDashboard },
  { href: "/fiscal", label: "Análise fiscal", role: "fiscal", icon: Scale },
  { href: "/integracoes", label: "Integrações", icon: Plug },
  { href: "/gerente/publicacao", label: "Publicação", role: "manager", icon: FolderSync },
];

function matches(item: NavItem, pathname: string): boolean {
  if (item.exact) return pathname === item.href;
  return pathname === item.href || pathname.startsWith(item.href + "/");
}

/** Um único item ativo: com rotas aninhadas (`/gerente` e `/gerente/publicacao`), vence o prefixo mais específico. */
export function isActive(item: NavItem, pathname: string | null): boolean {
  if (pathname === null || !matches(item, pathname)) return false;
  return !NAV_ITEMS.some(other => other !== item && matches(other, pathname) && other.href.length > item.href.length);
}

export function activeItem(pathname: string | null): NavItem | undefined {
  return NAV_ITEMS.find(item => isActive(item, pathname));
}
