import { publicEnv } from "@/lib/env";
import { createApiSource } from "@/lib/data/api-source";
import { createMockSource } from "@/lib/data/mock-source";
import type { DataSource } from "@/lib/data/source";

/** Único ponto de troca mock ↔ API (NEXT_PUBLIC_DATA_SOURCE). */
export const dataSource: DataSource =
  publicEnv.NEXT_PUBLIC_DATA_SOURCE === "api"
    ? createApiSource({ projectId: publicEnv.NEXT_PUBLIC_BASHO_PROJECT_ID })
    : createMockSource();

export { DataSourceError } from "@/lib/data/source";
export type { DataSource } from "@/lib/data/source";
