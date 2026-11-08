import type { AppState } from "../types";
import { reconcile } from "./simulationService";
import { isAppState, validReferences } from "./stateValidation";
export const STORAGE_KEY = "basho-demo-v2";
function record(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}
export function decodeState(raw: string): AppState {
  const envelope: unknown = JSON.parse(raw);
  if (
    !record(envelope) ||
    envelope.version !== 2 ||
    !isAppState(envelope.state)
  )
    throw new Error("Formato de demonstração incompatível ou inválido");
  const state = envelope.state;
  for (const rows of Object.values(state)) {
    if (
      Array.isArray(rows) &&
      new Set(rows.map((row) => row.id)).size !== rows.length
    )
      throw new Error("Identificadores duplicados no armazenamento");
  }
  if (!validReferences(state))
    throw new Error("Referências inconsistentes no armazenamento");
  return reconcile(state);
}
export function encodeState(state: AppState): string {
  return JSON.stringify({ version: 2, state });
}
