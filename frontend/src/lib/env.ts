import { z } from "zod";

const DEFAULT_API_URL = "http://localhost:8000";

const publicEnvSchema = z.object({
  NEXT_PUBLIC_API_URL: z.url().default(DEFAULT_API_URL),
  /** `mock` = dados sintéticos de demonstração; `api` = backend real. */
  NEXT_PUBLIC_DATA_SOURCE: z.enum(["mock", "api"]).default("mock"),
});

export const publicEnv = publicEnvSchema.parse({
  NEXT_PUBLIC_API_URL: process.env.NEXT_PUBLIC_API_URL,
  NEXT_PUBLIC_DATA_SOURCE: process.env.NEXT_PUBLIC_DATA_SOURCE,
});
