import { FlaskConical, House, LayoutDashboard, Plug, Scale, type LucideIcon } from "lucide-react";

export interface NavItem {
  href: string;
  label: string;
  /** Quem representa na demonstração (troca de papel não é autenticação). */
  person?: string;
  icon: LucideIcon;
  /** Só ativo na rota exata (o início não pode ficar ativo em todas as telas). */
  exact?: boolean;
}

export const NAV_ITEMS: readonly NavItem[] = [
  { href: "/", label: "Início", icon: House, exact: true },
  { href: "/pesquisador", label: "Pesquisador", person: "Ana Ribeiro / Bruno Costa", icon: FlaskConical },
  { href: "/gerente", label: "Gerente", person: "Marina Duarte", icon: LayoutDashboard },
  { href: "/gerente/integracoes", label: "Integrações", person: "Drive, Notion e GitHub", icon: Plug },
  { href: "/fiscal", label: "Fiscal", person: "Rafael Lima", icon: Scale },
];

export function isActive(item: NavItem, pathname: string | null): boolean {
  if (pathname === null) return false;
  return item.exact ? pathname === item.href : pathname.startsWith(item.href);
}

export function activeItem(pathname: string | null): NavItem | undefined {
  return NAV_ITEMS.find((item) => isActive(item, pathname));
}
