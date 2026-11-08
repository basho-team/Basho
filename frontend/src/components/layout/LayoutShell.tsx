"use client";
import { usePathname } from "next/navigation";
import { useState, type ReactNode } from "react";
import { AppProvider, useApp } from "@/store/AppContext";
import { Sidebar } from "./Sidebar";
import { Topbar } from "./Topbar";
import { Menu, X } from "lucide-react";
const TITLES: Record<string, string> = {
  "/": "Visão geral",
  "/projetos": "Projetos",
  "/documentos": "Documentos e evidências",
  "/atividades": "Atividades",
  "/operacoes": "Central de Operações",
  "/aprovacoes": "Aprovações",
  "/integracoes": "Integrações",
  "/autonomia": "Autonomia e permissões",
  "/lei-do-bem": "Lei do Bem",
  "/auditoria": "Histórico e auditoria",
};
function Workspace({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const [menu, setMenu] = useState(false);
  const { ready, notice, storageError, dismiss } = useApp();
  return (
    <div className="flex h-dvh overflow-hidden">
      <div className="hidden shrink-0 lg:block">
        <Sidebar />
      </div>
      {menu && (
        <div
          className="fixed inset-0 z-40 flex bg-black/40 lg:hidden"
          onClick={() => setMenu(false)}
        >
          <div onClick={(e) => e.stopPropagation()}>
            <Sidebar onNavigate={() => setMenu(false)} />
          </div>
          <button
            className="p-4 text-white"
            aria-label="Fechar navegação"
            onClick={() => setMenu(false)}
          >
            <X />
          </button>
        </div>
      )}
      <div className="flex min-w-0 flex-1 flex-col">
        <div className="flex border-b bg-card">
          <button
            aria-label="Abrir navegação"
            onClick={() => setMenu(true)}
            className="px-3 lg:hidden"
          >
            <Menu className="h-5 w-5" />
          </button>
          <Topbar title={TITLES[pathname] ?? "Detalhes do projeto"} />
        </div>
        <main
          id="conteudo"
          className="flex-1 overflow-y-auto bg-muted/30 p-4 md:p-7 xl:p-9"
        >
          {storageError && (
            <div
              role="alert"
              className="mb-5 rounded-lg border border-amber-300 bg-amber-50 p-3 text-sm text-amber-900"
            >
              {storageError}
            </div>
          )}
          {ready ? (
            children
          ) : (
            <div role="status" className="p-10 text-sm text-muted-foreground">
              Carregando ambiente de demonstração…
            </div>
          )}
        </main>
        {notice && (
          <div
            role="status"
            className="fixed bottom-5 right-5 z-[60] flex max-w-[calc(100%-2.5rem)] items-center gap-4 rounded-xl border bg-card p-4 text-sm shadow-xl"
          >
            <span>{notice}</span>
            <button aria-label="Fechar mensagem" onClick={dismiss}>
              <X className="h-4 w-4" />
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
export function LayoutShell({ children }: { children: ReactNode }) {
  return (
    <AppProvider>
      <a href="#conteudo" className="sr-only focus:not-sr-only">
        Ir para o conteúdo
      </a>
      <Workspace>{children}</Workspace>
    </AppProvider>
  );
}
