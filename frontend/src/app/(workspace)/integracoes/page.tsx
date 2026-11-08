import { IntegrationsView } from "@/components/integrations/integrations-view";
import { OrgSourcesPanel } from "@/components/sources/org-sources-panel";
import { publicEnv } from "@/lib/env";

/**
 * Com backend (`api` + projeto): GitHub, Notion e Drive reais do ledger (ADR-0012).
 * Na demonstração local (`mock`) não há backend: mostra as prévias sintéticas.
 */
export default function IntegrationsPage() {
  const live = publicEnv.NEXT_PUBLIC_DATA_SOURCE === "api" && publicEnv.NEXT_PUBLIC_BASHO_PROJECT_ID !== undefined;
  return live ? <OrgSourcesPanel /> : <IntegrationsView />;
}
