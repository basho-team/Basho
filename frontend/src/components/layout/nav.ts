import { FlaskConical, House, LayoutDashboard, Plug, Scale, type LucideIcon } from "lucide-react";
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
];

export function isActive(item: NavItem, pathname: string | null): boolean {
  if (pathname === null) return false;
  return item.exact ? pathname === item.href : pathname.startsWith(item.href);
}

export function activeItem(pathname: string | null): NavItem | undefined {
  return NAV_ITEMS.find(item => isActive(item, pathname));
}
