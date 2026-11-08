import { Badge } from "@/components/ui/badge";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import type { Expense } from "@/lib/contracts/provisional";

const RECONCILIATION_LABEL: Record<Expense["reconciliation_state"], string> = {
  unreconciled: "Não conciliada",
  matched: "Conciliada",
  duplicate_suspected: "Possível duplicidade",
  excluded: "Excluída",
};

/** Só formatação de exibição; nenhuma soma ou cálculo fiscal na UI. */
function formatAmount(amount: string | null, currency: string): string {
  if (amount === null) return "Não informado";
  return new Intl.NumberFormat("pt-BR", { style: "currency", currency }).format(Number(amount));
}

function allocationText(expense: Expense): string {
  if (expense.allocations.length === 0) return "—";
  return expense.allocations
    .map((a) => `${a.target_label}: ${a.share ?? "parcela não definida"} (${a.basis ?? "sem critério"})`)
    .join("; ");
}

export function ExpensesTable({ expenses }: { expenses: Expense[] }) {
  return (
    <div className="overflow-x-auto rounded-lg border">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Documento</TableHead>
            <TableHead>Valor</TableHead>
            <TableHead>Conciliação</TableHead>
            <TableHead>Alocação</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {expenses.map((e) => (
            <TableRow key={e.id} className={e.reconciliation_state === "excluded" ? "text-muted-foreground" : undefined}>
              <TableCell className="whitespace-normal">
                <div className="flex flex-wrap items-center gap-2 font-medium">
                  {e.document}
                </div>
                <div className="text-xs text-muted-foreground">{e.item}</div>
                {e.excluded_reason && <div className="text-xs">Motivo da exclusão: {e.excluded_reason}</div>}
              </TableCell>
              <TableCell className={e.amount === null ? "italic" : undefined}>
                {formatAmount(e.amount, e.currency)}
              </TableCell>
              <TableCell>
                <Badge variant="outline">{RECONCILIATION_LABEL[e.reconciliation_state]}</Badge>
              </TableCell>
              <TableCell className="text-xs whitespace-normal">{allocationText(e)}</TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}
