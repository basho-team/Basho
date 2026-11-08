"use client";
import {
  createContext,
  useContext,
  useEffect,
  useState,
  useSyncExternalStore,
  type ReactNode,
} from "react";
import { createDemoStore, type StoreSnapshot } from "./demoStore";
type DemoStore = ReturnType<typeof createDemoStore>;
type AppContextValue = StoreSnapshot &
  Pick<DemoStore, "transact" | "execute" | "resetData" | "dismiss">;
const AppContext = createContext<AppContextValue | null>(null);
export function AppProvider({ children }: { children: ReactNode }) {
  const [store] = useState(createDemoStore);
  const snapshot = useSyncExternalStore(
    store.subscribe,
    store.getSnapshot,
    store.getServerSnapshot,
  );
  useEffect(() => store.mount(), [store]);
  return (
    <AppContext.Provider
      value={{
        ...snapshot,
        transact: store.transact,
        execute: store.execute,
        resetData: store.resetData,
        dismiss: store.dismiss,
      }}
    >
      {children}
    </AppContext.Provider>
  );
}
export function useApp() {
  const context = useContext(AppContext);
  if (!context) throw new Error("AppProvider ausente");
  return context;
}
