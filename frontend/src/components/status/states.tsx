import { AlertTriangle, Clock, Hourglass, Inbox, Loader2 } from "lucide-react";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { DataSourceError } from "@/lib/data/source";

export function LoadingState({ label = "Carregando…" }: { label?: string }) {
  return (
    <div role="status" className="flex items-center gap-2 py-6 text-sm text-muted-foreground">
      <Loader2 className="size-4 animate-spin" aria-hidden />
      {label}
    </div>
  );
}

/** Erro visível: a UI nunca finge sucesso quando a fonte de dados falha. */
export function ErrorState({ error, onRetry }: { error: unknown; onRetry?: () => void }) {
  const detail = error instanceof DataSourceError ? error.error : null;
  return (
    <Alert variant="destructive">
      <AlertTriangle aria-hidden />
      <AlertTitle>{detail ? "Não foi possível concluir" : "Erro inesperado"}</AlertTitle>
      <AlertDescription>
        <p>{detail?.message ?? "Algo deu errado. Tente de novo ou avise a equipe."}</p>
        {detail && (
          <p className="font-mono text-xs">
            código {detail.code} · correlação {detail.correlation_id}
          </p>
        )}
        {onRetry && (detail?.retryable ?? true) && (
          <Button size="sm" variant="outline" className="mt-2" onClick={onRetry}>
            Tentar de novo
          </Button>
        )}
      </AlertDescription>
    </Alert>
  );
}

export function EmptyState({ title, children }: { title: string; children?: React.ReactNode }) {
  return (
    <div className="flex flex-col items-center gap-2 rounded-lg border border-dashed px-4 py-8 text-center text-sm text-muted-foreground">
      <Inbox className="size-5" aria-hidden />
      <p className="font-medium text-foreground">{title}</p>
      {children}
    </div>
  );
}

/** Espera humana: o fluxo está parado aguardando alguém, não processando. */
export function AwaitingState({ title, children }: { title: string; children?: React.ReactNode }) {
  return (
    <Alert>
      <Hourglass aria-hidden />
      <AlertTitle>{title}</AlertTitle>
      {children && <AlertDescription>{children}</AlertDescription>}
    </Alert>
  );
}

export function StaleBanner({ reason }: { reason: string }) {
  return (
    <Alert className="border-amber-300 bg-amber-50 text-amber-950 dark:border-amber-800 dark:bg-amber-950 dark:text-amber-100">
      <Clock aria-hidden />
      <AlertTitle>Conteúdo desatualizado</AlertTitle>
      <AlertDescription className="text-inherit">{reason}</AlertDescription>
    </Alert>
  );
}
