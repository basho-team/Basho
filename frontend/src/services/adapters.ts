import type { AppState, SimulationCommand, SimulationResult } from "../types";
import { executeCommand } from "./simulationService";
// Replace this implementation at the application boundary when real connectors are authorized.
// No network access, credentials, OAuth or LLM calls exist in this adapter.
export interface OperationsAdapter {
  execute(
    state: AppState,
    command: SimulationCommand,
    context?: Parameters<typeof executeCommand>[2],
  ): SimulationResult;
}
export const simulatedAdapter: OperationsAdapter = { execute: executeCommand };
