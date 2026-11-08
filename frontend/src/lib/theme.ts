import { useSyncExternalStore } from "react";
import { DARK_QUERY, THEME_STORAGE_KEY } from "./theme-script";

/** Preferência salva. `system` segue o sistema operacional e é o padrão (nada salvo). */
export type ThemePreference = "light" | "dark" | "system";
export type ResolvedTheme = "light" | "dark";

const listeners = new Set<() => void>();

export function readPreference(): ThemePreference {
  try {
    const stored = localStorage.getItem(THEME_STORAGE_KEY);
    return stored === "light" || stored === "dark" ? stored : "system";
  } catch {
    // Armazenamento bloqueado (janela privada, política): segue o sistema.
    return "system";
  }
}

export function resolveTheme(preference: ThemePreference): ResolvedTheme {
  if (preference !== "system") return preference;
  return matchMedia(DARK_QUERY).matches ? "dark" : "light";
}

export function applyTheme(preference: ThemePreference): void {
  const resolved = resolveTheme(preference);
  const root = document.documentElement;
  root.classList.toggle("dark", resolved === "dark");
  root.style.colorScheme = resolved;
}

export function setPreference(preference: ThemePreference): void {
  try {
    if (preference === "system") localStorage.removeItem(THEME_STORAGE_KEY);
    else localStorage.setItem(THEME_STORAGE_KEY, preference);
  } catch {
    // Sem armazenamento: o tema vale só nesta página.
  }
  applyTheme(preference);
  listeners.forEach((listener) => listener());
}

function subscribe(onChange: () => void): () => void {
  listeners.add(onChange);
  const media = matchMedia(DARK_QUERY);
  const onSystemChange = () => {
    if (readPreference() === "system") applyTheme("system");
    onChange();
  };
  // Outra aba mudou o tema.
  const onStorage = (event: StorageEvent) => {
    if (event.key !== null && event.key !== THEME_STORAGE_KEY) return;
    applyTheme(readPreference());
    onChange();
  };
  media.addEventListener("change", onSystemChange);
  window.addEventListener("storage", onStorage);
  return () => {
    listeners.delete(onChange);
    media.removeEventListener("change", onSystemChange);
    window.removeEventListener("storage", onStorage);
  };
}

/** No servidor e na hidratação vale `system`; o valor real entra logo após, sem erro de hidratação. */
export function useThemePreference(): ThemePreference {
  return useSyncExternalStore(subscribe, readPreference, () => "system");
}
