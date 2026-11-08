import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import { applyTheme, readPreference, resolveTheme, setPreference } from "@/lib/theme";
import { THEME_INIT_SCRIPT, THEME_STORAGE_KEY } from "@/lib/theme-script";

interface Env {
  store: Map<string, string>;
  classes: Set<string>;
  root: { classList: { toggle: (name: string, on: boolean) => void }; style: { colorScheme: string } };
}

/** Navegador mínimo: localStorage, matchMedia e <html>. `osDark` é a preferência do sistema. */
function stubBrowser(osDark: boolean, storage: "ok" | "blocked" = "ok"): Env {
  const store = new Map<string, string>();
  const classes = new Set<string>();
  const root = {
    classList: {
      toggle: (name: string, on: boolean) => {
        if (on) classes.add(name);
        else classes.delete(name);
      },
    },
    style: { colorScheme: "" },
  };
  const blocked = () => {
    throw new Error("storage bloqueado");
  };
  vi.stubGlobal("document", { documentElement: root });
  vi.stubGlobal("matchMedia", () => ({ matches: osDark, addEventListener: vi.fn(), removeEventListener: vi.fn() }));
  vi.stubGlobal("window", { addEventListener: vi.fn(), removeEventListener: vi.fn() });
  vi.stubGlobal(
    "localStorage",
    storage === "blocked"
      ? { getItem: blocked, setItem: blocked, removeItem: blocked }
      : {
          getItem: (key: string) => store.get(key) ?? null,
          setItem: (key: string, value: string) => void store.set(key, value),
          removeItem: (key: string) => void store.delete(key),
        },
  );
  return { store, classes, root };
}

/** Executa o script do <head> como o navegador, no ambiente simulado. */
function runInitScript(): void {
  new Function(THEME_INIT_SCRIPT)();
}

beforeEach(() => vi.unstubAllGlobals());
afterEach(() => vi.unstubAllGlobals());

describe("script de inicialização (antes da primeira pintura)", () => {
  test.each([
    { saved: "dark", osDark: false, dark: true },
    { saved: "light", osDark: true, dark: false },
    { saved: null, osDark: true, dark: true },
    { saved: null, osDark: false, dark: false },
  ])("salvo=$saved, sistema escuro=$osDark → escuro=$dark", ({ saved, osDark, dark }) => {
    // Arrange
    const env = stubBrowser(osDark);
    if (saved) env.store.set(THEME_STORAGE_KEY, saved);

    // Act
    runInitScript();

    // Assert
    expect(env.classes.has("dark")).toBe(dark);
    expect(env.root.style.colorScheme).toBe(dark ? "dark" : "light");
  });

  test("valor salvo inválido cai no sistema", () => {
    const env = stubBrowser(true);
    env.store.set(THEME_STORAGE_KEY, "roxo");
    runInitScript();
    expect(env.classes.has("dark")).toBe(true);
  });

  test("armazenamento bloqueado não quebra a página", () => {
    stubBrowser(true, "blocked");
    expect(() => runInitScript()).not.toThrow();
  });
});

describe("alternador", () => {
  test("escolher escuro persiste e aplica, mesmo com o sistema claro", () => {
    const env = stubBrowser(false);
    setPreference("dark");
    expect(env.store.get(THEME_STORAGE_KEY)).toBe("dark");
    expect(env.classes.has("dark")).toBe(true);
    expect(readPreference()).toBe("dark");
  });

  test("escolher claro vence o sistema escuro", () => {
    const env = stubBrowser(true);
    setPreference("light");
    expect(env.classes.has("dark")).toBe(false);
    expect(readPreference()).toBe("light");
  });

  test("sistema remove a preferência salva e volta a seguir o SO", () => {
    const env = stubBrowser(true);
    setPreference("light");
    setPreference("system");
    expect(env.store.has(THEME_STORAGE_KEY)).toBe(false);
    expect(readPreference()).toBe("system");
    expect(env.classes.has("dark")).toBe(true);
  });

  test("sem armazenamento o tema ainda é aplicado na página", () => {
    const env = stubBrowser(false, "blocked");
    expect(() => setPreference("dark")).not.toThrow();
    expect(env.classes.has("dark")).toBe(true);
    expect(readPreference()).toBe("system");
  });

  test("applyTheme e resolveTheme concordam", () => {
    const env = stubBrowser(true);
    expect(resolveTheme("system")).toBe("dark");
    expect(resolveTheme("light")).toBe("light");
    applyTheme("light");
    expect(env.classes.has("dark")).toBe(false);
  });
});
