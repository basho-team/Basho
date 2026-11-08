// @vitest-environment jsdom
import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, test } from "vitest";
import { SessionProvider } from "@/components/auth/session-provider";
import { SourcesPanel } from "@/components/demo-sources/sources-panel";
import { accountUser, DEMO_ACCOUNTS } from "@/lib/auth/shared";
import { EXAMPLE_LINKS } from "@/lib/demo-sources/links";

const EQUIPE = DEMO_ACCOUNTS.find(account => account.id === "equipe")!;

function setup(stepDelayMs = 0) {
  const user = userEvent.setup();
  const view = render(
    <SessionProvider user={accountUser(EQUIPE)}>
      <SourcesPanel stepDelayMs={stepDelayMs} />
    </SessionProvider>,
  );
  return { user, view };
}

async function connectExamples(user: ReturnType<typeof userEvent.setup>) {
  await user.click(screen.getByRole("button", { name: "Preencher com exemplos" }));
  await user.click(screen.getByRole("button", { name: "Conectar tudo" }));
}

/** Espera o fim dos passos: o relatório (e a seção de fontes) só aparece quando termina. */
async function finishRun() {
  await waitFor(() => expect(screen.getByRole("heading", { name: "Fontes" })).toBeTruthy(), { timeout: 4000 });
}

beforeEach(() => {
  window.localStorage.clear();
});
afterEach(() => {
  cleanup();
});

describe("Minhas fontes (pesquisador de demonstração)", () => {
  test("a conta nova é pesquisadora e o fluxo começa sem nada conectado", () => {
    expect(EQUIPE.role).toBe("researcher");
    setup();
    expect(screen.getByText(/Simulação de demonstração/)).toBeTruthy();
    expect((screen.getByRole("button", { name: /Gerar e publicar relatório/ }) as HTMLButtonElement).disabled).toBe(true);
  });

  test("link de outro serviço no campo do GitHub é recusado, com mensagem, e não conecta", async () => {
    const { user } = setup();
    await user.type(screen.getByLabelText("Link: Repositório do GitHub"), "https://evil.example/a/b");
    await user.click(within(document.querySelector('[data-source="github"]') as HTMLElement).getByRole("button", { name: "Conectar" }));
    expect(screen.getByRole("alert").textContent).toMatch(/não é do GitHub/);
    expect(screen.queryByText("Conectado (simulado)")).toBeNull();
  });

  test("link malicioso de metadados de nuvem não é aceito em nenhum campo", async () => {
    const { user } = setup();
    await user.type(screen.getByLabelText("Link: Pasta do Google Drive"), "https://169.254.169.254/latest/meta-data/");
    await user.click(within(document.querySelector('[data-source="drive"]') as HTMLElement).getByRole("button", { name: "Conectar" }));
    expect(screen.getByRole("alert").textContent).toMatch(/não é do Google Drive/);
  });

  test("exemplos: preenche, conecta os três e libera a geração", async () => {
    const { user } = setup();
    await connectExamples(user);
    expect(screen.getAllByText("Conectado (simulado)")).toHaveLength(3);
    expect(screen.getByText("equipe-basho/calibracao-sensores")).toBeTruthy();
    expect((screen.getByRole("button", { name: /Gerar e publicar relatório/ }) as HTMLButtonElement).disabled).toBe(false);
  });

  test("a plataforma atua: publica em BASHO no Drive e no Notion e mostra o relatório com fontes e pendências", async () => {
    const { user } = setup(60);
    await connectExamples(user);
    await user.click(screen.getByRole("button", { name: /Gerar e publicar relatório/ }));
    expect(screen.getByRole("button", { name: /Trabalhando/ })).toBeTruthy();
    await finishRun();

    const drive = document.querySelector('[data-published="drive"]') as HTMLElement;
    const notion = document.querySelector('[data-published="notion"]') as HTMLElement;
    for (const card of [drive, notion]) {
      expect(within(card).getByText("BASHO")).toBeTruthy();
      expect(within(card).getByText(/Relatório BASHO — calibracao-sensores — /)).toBeTruthy();
      expect(within(card).getByText("Publicado (simulado)")).toBeTruthy();
    }
    expect(screen.getByRole("heading", { name: /Pendências para os responsáveis/ })).toBeTruthy();
    expect(screen.getByRole("heading", { name: "Fontes" })).toBeTruthy();
    expect(screen.getByRole("heading", { name: /O que a plataforma não fez/ })).toBeTruthy();
    expect(screen.getAllByText(/Dado sintético/).length).toBeGreaterThan(0);
  });

  test("sem Notion conectado, só o Drive recebe o documento e o passo do Notion é pulado", async () => {
    const { user } = setup();
    await user.click(screen.getByRole("button", { name: "Preencher com exemplos" }));
    await user.click(within(document.querySelector('[data-source="github"]') as HTMLElement).getByRole("button", { name: "Conectar" }));
    await user.click(within(document.querySelector('[data-source="drive"]') as HTMLElement).getByRole("button", { name: "Conectar" }));
    await user.click(screen.getByRole("button", { name: /Gerar e publicar relatório/ }));
    await finishRun();
    expect(document.querySelector('[data-published="drive"]')).not.toBeNull();
    expect(document.querySelector('[data-published="notion"]')).toBeNull();
    expect(screen.getByText(/não conectado, pulado/)).toBeTruthy();
  });

  test("sem GitHub não há o que gerar", async () => {
    const { user } = setup();
    await user.click(screen.getByRole("button", { name: "Preencher com exemplos" }));
    await user.click(within(document.querySelector('[data-source="drive"]') as HTMLElement).getByRole("button", { name: "Conectar" }));
    expect((screen.getByRole("button", { name: /Gerar e publicar relatório/ }) as HTMLButtonElement).disabled).toBe(true);
    expect(screen.getByText(/Conecte um repositório do GitHub/)).toBeTruthy();
  });

  test("ao recarregar, as fontes e o resultado voltam (só os links ficam no navegador)", async () => {
    const first = setup();
    await connectExamples(first.user);
    await first.user.click(screen.getByRole("button", { name: /Gerar e publicar relatório/ }));
    await finishRun();
    first.view.unmount();

    setup();
    expect(screen.getAllByText("Conectado (simulado)")).toHaveLength(3);
    expect(document.querySelector('[data-published="drive"]')).not.toBeNull();
    const stored = JSON.parse(window.localStorage.getItem("basho-demo-sources:equipe") ?? "{}");
    expect(stored.urls.github).toBe(EXAMPLE_LINKS.github);
    expect(JSON.stringify(stored)).not.toContain("Relatório BASHO"); // o relatório é refeito, não guardado
  });

  test("Recomeçar limpa tudo, inclusive o que ficou guardado", async () => {
    const { user } = setup();
    await connectExamples(user);
    await user.click(screen.getByRole("button", { name: "Recomeçar" }));
    expect(screen.queryByText("Conectado (simulado)")).toBeNull();
    expect(JSON.parse(window.localStorage.getItem("basho-demo-sources:equipe") ?? "{}").urls).toEqual({});
  });
});
