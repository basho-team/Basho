/**
 * SIMULAÇÃO: resultado roteirizado da reanálise após uma resposta. Na API real, isso vem
 * do módulo fiscal de Thiago. A nota mista NUNCA vira elegível por inteiro só porque
 * houve resposta (EXECUCAO_E_ACEITE.md).
 */
import type { Finding } from "@/lib/contracts/provisional";

type Outcome = Pick<Finding, "signal" | "justification" | "gaps" | "next_step">;

export const REANALYSIS_OUTCOMES: Record<string, Outcome> = {
  "f-desp-nf1023": {
    signal: "fiscal_judgment_required",
    justification:
      "Critério de alocação recebido. A parcela proposta depende de julgamento fiscal; a nota não é considerada elegível por inteiro.",
    gaps: ["Validar se o critério informado sustenta a parcela alocada ao projeto."],
    next_step: "Fiscal decide sobre a parcela alocada.",
  },
  "f-horas-ana": {
    signal: "supported_by_evidence",
    justification: "Registro formal de horas declarado pela pesquisadora, com fonte indicada.",
    gaps: [],
    next_step: "Fiscal confere a fonte declarada.",
  },
  default: {
    signal: "fiscal_judgment_required",
    justification: "Nova evidência recebida; a conclusão exige interpretação fiscal.",
    gaps: [],
    next_step: "Fiscal avalia a nova evidência.",
  },
};
