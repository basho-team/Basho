import { z } from "zod";

const DEFAULT_API_URL = "http://localhost:8000";

const publicEnvSchema = z.object({
  NEXT_PUBLIC_API_URL: z.url().default(DEFAULT_API_URL),
});

export const publicEnv = publicEnvSchema.parse({
  NEXT_PUBLIC_API_URL: process.env.NEXT_PUBLIC_API_URL,
});
