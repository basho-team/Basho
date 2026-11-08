"use client";
import { useApp } from "@/store/AppContext";
import { Badge } from "@/components/ui/badge";
import { RotateCcw, FlaskConical } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
  DialogClose,
} from "@/components/ui/dialog";

export function Topbar({ title }: { title: string }) {
  const { state, resetData } = useApp();

  const activeIntegrations = state.integrations.filter(
    (i) => i.status === "connected",
  ).length;
  const pendingApprovals = state.approvalRequests.filter(
    (a) => a.status === "pending",
  ).length;

  return (
    <header className="flex min-h-20 min-w-0 flex-1 flex-wrap items-center justify-between gap-3 bg-card px-4 py-3 md:px-7">
      <div>
        <h1 className="text-base font-semibold tracking-tight">{title}</h1>
        <p className="text-xs text-muted-foreground">
          {state.organization.name} · Ano-base {state.organization.taxYear}
        </p>
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <Badge variant="info" className="hidden sm:inline-flex">
          Integrações: {activeIntegrations}/3
        </Badge>
        {pendingApprovals > 0 && (
          <Badge variant="warning" className="hidden md:inline-flex">
            {pendingApprovals} aprovaç{pendingApprovals === 1 ? "ão" : "ões"}{" "}
            pendente{pendingApprovals === 1 ? "" : "s"}
          </Badge>
        )}
        <Badge variant="outline" className="gap-1">
          <FlaskConical className="h-3 w-3" /> Demo
        </Badge>

        <Dialog>
          <DialogTrigger asChild>
            <Button variant="outline" size="sm" className="gap-2">
              <RotateCcw className="h-4 w-4" /> Restaurar dados
            </Button>
          </DialogTrigger>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>Restaurar dados de demonstração?</DialogTitle>
              <DialogDescription>
                Esta ação substituirá todas as alterações feitas (documentos,
                atividades, execuções, aprovações e logs) pelos dados sintéticos
                iniciais. Não pode ser desfeita.
              </DialogDescription>
            </DialogHeader>
            <DialogFooter>
              <DialogClose asChild>
                <Button variant="outline">Cancelar</Button>
              </DialogClose>
              <DialogClose asChild>
                <Button variant="destructive" onClick={resetData}>
                  Restaurar
                </Button>
              </DialogClose>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      </div>
    </header>
  );
}
