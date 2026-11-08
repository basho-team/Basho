"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  LayoutDashboard,
  FolderKanban,
  FileText,
  ListTodo,
  Cpu,
  ShieldCheck,
  Plug,
  Settings2,
  History,
  ScrollText,
  FlaskConical,
} from "lucide-react";
import { cn } from "@/lib/utils";

const navItems = [
  { href: "/", label: "Visão Geral", icon: LayoutDashboard },
  { href: "/projetos", label: "Projetos", icon: FolderKanban },
  { href: "/documentos", label: "Documentos e Evidências", icon: FileText },
  { href: "/atividades", label: "Atividades", icon: ListTodo },
  { href: "/operacoes", label: "Central de Operações", icon: Cpu },
  { href: "/aprovacoes", label: "Aprovações", icon: ShieldCheck },
  { href: "/integracoes", label: "Integrações", icon: Plug },
  { href: "/autonomia", label: "Configurações de Autonomia", icon: Settings2 },
  { href: "/lei-do-bem", label: "Lei do Bem", icon: FlaskConical },
  { href: "/auditoria", label: "Histórico e Auditoria", icon: History },
];

export function Sidebar({ onNavigate }: { onNavigate?: () => void }) {
  const pathname = usePathname();

  return (
    <aside className="flex h-dvh w-64 flex-col border-r bg-sidebar">
      <div className="flex h-16 items-center gap-2 border-b px-6">
        <ScrollText className="h-7 w-7 text-primary" />
        <div className="flex flex-col">
          <span className="text-lg font-bold tracking-tight">Basho</span>
          <span className="text-[10px] text-muted-foreground">
            Gestão de inovação
          </span>
        </div>
      </div>

      <nav className="flex-1 overflow-y-auto p-3">
        <ul className="space-y-1">
          {navItems.map((item) => {
            const isActive =
              pathname === item.href ||
              (item.href !== "/" && pathname.startsWith(item.href));
            const Icon = item.icon;
            return (
              <li key={item.href}>
                <Link
                  href={item.href}
                  onClick={onNavigate}
                  aria-current={isActive ? "page" : undefined}
                  className={cn(
                    "flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors",
                    isActive
                      ? "bg-emerald-900 text-white shadow-sm"
                      : "text-muted-foreground hover:bg-sidebar-accent/50 hover:text-sidebar-foreground",
                  )}
                >
                  <Icon className="h-4 w-4 shrink-0" />
                  {item.label}
                </Link>
              </li>
            );
          })}
        </ul>
      </nav>

      <div className="border-t p-4">
        <div className="rounded-lg bg-amber-500/10 px-3 py-2 text-xs text-amber-700 dark:text-amber-400">
          <span className="font-semibold">⚠ Ambiente de demonstração</span>
          <br />
          Dados sintéticos. Integrações simuladas.
        </div>
      </div>
    </aside>
  );
}
