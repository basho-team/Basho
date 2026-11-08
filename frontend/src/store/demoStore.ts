import type { AppState, SimulationCommand } from "../types";
import { createInitialState } from "../data/seedData";
import { reconcile } from "../services/simulationService";
import { simulatedAdapter } from "../services/adapters";
import { advanceRun } from "../services/workflowEngine";
import {
  decodeState,
  encodeState,
  STORAGE_KEY,
} from "../services/persistenceService";

export interface StoreSnapshot {
  state: AppState;
  ready: boolean;
  notice: string;
  storageError: string;
}
export function createDemoStore() {
  const initial: StoreSnapshot = {
    state: reconcile(createInitialState()),
    ready: false,
    notice: "",
    storageError: "",
  };
  let snapshot = initial;
  const listeners = new Set<() => void>();
  const emit = () => listeners.forEach((listener) => listener());
  function save() {
    if (!snapshot.ready || snapshot.storageError) return;
    try {
      localStorage.setItem(STORAGE_KEY, encodeState(snapshot.state));
    } catch {
      snapshot = {
        ...snapshot,
        storageError:
          "Armazenamento indisponível ou cheio. As alterações estão apenas nesta sessão. Libere espaço e restaure a demonstração para tentar novamente.",
      };
    }
  }
  function update(patch: Partial<StoreSnapshot>, persist = false) {
    snapshot = { ...snapshot, ...patch };
    if (persist) save();
    emit();
  }
  function transact(
    action: (state: AppState) => AppState,
    message = "Alterações salvas",
  ) {
    try {
      update(
        {
          state: action(snapshot.state),
          ...(message ? { notice: message } : {}),
        },
        true,
      );
      return true;
    } catch (error) {
      update({
        notice:
          error instanceof Error
            ? error.message
            : "Não foi possível concluir a operação",
      });
      return false;
    }
  }
  function execute(command: SimulationCommand) {
    try {
      const result = simulatedAdapter.execute(snapshot.state, command);
      update({ state: result.state, notice: result.message }, true);
      return result.outcome !== "blocked";
    } catch {
      update({
        notice:
          "Não foi possível concluir a operação. Os dados foram preservados.",
      });
      return false;
    }
  }
  function mount() {
    try {
      const raw = localStorage.getItem(STORAGE_KEY);
      update({ state: raw ? decodeState(raw) : snapshot.state, ready: true });
    } catch {
      update({
        ready: true,
        storageError:
          "Não foi possível carregar os dados locais. A demonstração inicial está disponível; restaure os dados para substituir o armazenamento inválido.",
      });
    }
    const timer = setInterval(() => {
      const runs = snapshot.state.agentRuns.filter(
        (r) => r.status === "running",
      );
      if (runs.length)
        transact(
          (state) =>
            runs.reduce((next, run) => advanceRun(next, run.id), state),
          "",
        );
    }, 450);
    return () => clearInterval(timer);
  }
  return {
    subscribe: (listener: () => void) => {
      listeners.add(listener);
      return () => {
        listeners.delete(listener);
      };
    },
    getSnapshot: () => snapshot,
    getServerSnapshot: () => initial,
    mount,
    transact,
    execute,
    resetData: () =>
      update(
        {
          state: reconcile(createInitialState()),
          storageError: "",
          notice: "Dados de demonstração restaurados",
        },
        true,
      ),
    dismiss: () => update({ notice: "" }),
  };
}
