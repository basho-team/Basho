"use client";

import { createContext, useContext } from "react";
import type { DemoUser } from "@/lib/auth/shared";

const SessionContext = createContext<DemoUser | null>(null);

export function SessionProvider({ user, children }: { user: DemoUser; children: React.ReactNode }) {
  return <SessionContext.Provider value={user}>{children}</SessionContext.Provider>;
}

export function useDemoUser(): DemoUser {
  const user = useContext(SessionContext);
  if (!user) throw new Error("Sessão da demonstração ausente.");
  return user;
}
