import { publicEnv } from "@/lib/env";
import { createApiSource } from "@/lib/data/api-source";
import { createDemoSource } from "@/lib/data/demo-source";
import type { DataSource } from "@/lib/data/source";

/** Único ponto de troca mock ↔ API (NEXT_PUBLIC_DATA_SOURCE). */
export const dataSource: DataSource =
  publicEnv.NEXT_PUBLIC_DATA_SOURCE === "api"
    ? createApiSource({ projectId: publicEnv.NEXT_PUBLIC_BASHO_PROJECT_ID })
    : createDemoSource();

export { DataSourceError } from "@/lib/data/source";
export type { DataSource } from "@/lib/data/source";
