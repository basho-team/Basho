import { z } from "zod";

export const ProviderSchema = z.enum(["github", "notion", "drive"]);
export type IntegrationProvider = z.infer<typeof ProviderSchema>;
export const IntegrationSourceSchema = z.object({
  id: z.string(), title: z.string(), locator: z.string(), revision: z.string(), excerpt: z.string(),
  ownerId: z.string().nullable(), isSynthetic: z.literal(true),
});
export const IntegrationSchema = z.object({
  provider: ProviderSchema, name: z.string(), enabled: z.boolean(), canConfigure: z.boolean(),
  implementation: z.string(), checkedAt: z.string().nullable(), sources: z.array(IntegrationSourceSchema),
});
export const IntegrationOverviewSchema = z.object({ integrations: z.array(IntegrationSchema), mode: z.literal("demo") });
export type IntegrationOverview = z.infer<typeof IntegrationOverviewSchema>;
export const IntegrationActionSchema = z.object({
  provider: ProviderSchema, action: z.enum(["verify", "sync", "enable", "disable"]),
}).strict();
