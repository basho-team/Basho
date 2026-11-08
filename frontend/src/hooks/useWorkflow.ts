"use client";
import { useApp } from "@/store/AppContext";
import { receiveGithubEvent, startScenario } from "@/services/workflowEngine";
import type { GithubEventType, ScenarioId } from "@/types";
export function useWorkflow() {
  const { transact } = useApp();
  return {
    triggerScenario: (
      scenario: ScenarioId,
      projectId?: string,
      original = true,
    ) =>
      transact(
        (s) => startScenario(s, scenario, projectId, original),
        "Simulação iniciada. Acompanhe a linha do tempo.",
      ),
    triggerGithubEvent: (type: GithubEventType, repoId: string) =>
      transact(
        (s) => receiveGithubEvent(s, type, repoId),
        "Evento sintético recebido. Fluxos habilitados iniciam automaticamente.",
      ),
  };
}
