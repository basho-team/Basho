/** Só importado por rotas de servidor (BFF); nunca por componentes "use client". */
import { z } from "zod";

/** Variáveis só do servidor (BFF). Nunca expor ao navegador. */
const serverEnvSchema = z.object({
  BASHO_API_URL: z.url().default("http://127.0.0.1:8765"),
  REVIEWER_IDENTITY_SECRET: z.string().min(32).optional(),
});

export const serverEnv = serverEnvSchema.parse({
  BASHO_API_URL: process.env.BASHO_API_URL,
  REVIEWER_IDENTITY_SECRET: process.env.REVIEWER_IDENTITY_SECRET || undefined,
});
