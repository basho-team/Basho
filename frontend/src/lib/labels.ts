/** Rótulos em português para estados e códigos vindos da API. */
export const SECTION: Record<string, string> = {
  technological_challenge: "Desafio tecnológico",
  hypothesis: "Hipótese",
  method: "Método",
  result: "Resultado",
  uncertainty: "Incerteza",
};

export const CLAIM_STATUS: Record<string, string> = {
  supported: "Com evidência",
  pending: "Pendente",
  disputed: "Em conflito",
};

export const OUTCOME: Record<string, string> = {
  positive: "Positivo",
  negative: "Negativo",
  inconclusive: "Inconclusivo",
};

export const REVIEW_STATE: Record<string, string> = {
  text_approved: "Texto confirmado",
  changes_requested: "Correções pedidas",
  awaiting_review: "Aguardando revisão",
};

export const EVIDENCE_KIND: Record<string, string> = {
  activity_record: "Registro de atividade",
  technical_justification: "Justificativa técnica",
  formal_hours_declared: "Horas (registro formal)",
  user_correction: "Correção do usuário",
  commit_observed: "Commit (GitHub)",
  pull_request_observed: "Pull request (GitHub)",
  issue_observed: "Issue (GitHub)",
  verification_result: "Resultado de verificação",
  status_changed: "Mudança de estado",
};

export const DOSSIER_STATUS: Record<string, string> = {
  supported: "Sustentada por evidência citada",
  pending: "Pendente",
  disputed: "Conflitante",
  result_positive: "Resultado positivo",
  result_negative: "Resultado negativo",
  result_inconclusive: "Resultado inconclusivo",
  gap: "Lacuna",
};

export const GAP: Record<string, string> = {
  evidence_unresolved: "evidência não encontrada no ledger",
  evidence_out_of_scope: "evidência de outro projeto/tenant",
  evidence_superseded: "evidência substituída por versão posterior",
  no_evidence: "sem evidência citada",
  researcher_text_review_missing: "pesquisador ainda não confirmou o texto desta versão",
  researcher_approval_outdated: "confirmação refere-se a versão anterior",
  formal_hours_missing: "sem registro formal de horas",
  formal_hours_not_formal: "horas citadas não vêm de registro formal",
  period_outside_fiscal_year: "período fora do ano-base",
  period_spans_fiscal_years: "período cruza anos-base",
  open_question: "pergunta em aberto",
  evidence_conflict: "evidências em conflito",
};

export const PROHIBITED_NOTE =
  "O Basho não decide enquadramento, não garante benefício e não envia o FORMP&D. " +
  "Tudo aqui é potencialmente qualificável, sujeito a análise dos responsáveis.";

export function short(id: string | null | undefined): string {
  return id ? id.replace(/-/g, "").slice(0, 8) : "—";
}
