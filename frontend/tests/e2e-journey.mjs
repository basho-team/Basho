// E2E da jornada na interface real (Chromium headless via CDP; sem dependências novas).
// Pré-requisitos: API e frontend rodando, banco com o seed da demo e SEM relatório da Ana.
// Uso: BASHO_E2E_URL=http://127.0.0.1:3765 BASHO_E2E_BROWSER=/caminho/chrome node tests/e2e-journey.mjs
import { spawn } from "node:child_process";
import { mkdtemp, mkdir, readFile, rm, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import assert from "node:assert/strict";

const BASE = process.env.BASHO_E2E_URL ?? "http://127.0.0.1:3765";
const BROWSER = process.env.BASHO_E2E_BROWSER;
assert.ok(BROWSER, "defina BASHO_E2E_BROWSER com o binário do Chromium/Chrome");
const OUT = path.resolve(".qa");
const ANA = "33333333-3333-4333-8333-333333333333";
const BIA = "44444444-4444-4444-8444-444444444444";
const CARLA = "55555555-5555-4555-8555-555555555555";
const DAVI = "66666666-6666-4666-8666-666666666666";

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function launch() {
  const profile = await mkdtemp(path.join(os.tmpdir(), "basho-e2e-"));
  const proc = spawn(BROWSER, ["--headless=new", "--disable-gpu", "--no-first-run",
    "--remote-debugging-port=0", `--user-data-dir=${profile}`, "--window-size=1280,900", "about:blank"],
    { stdio: "ignore" });
  let port;
  for (let i = 0; i < 100 && !port; i++) {
    try { port = (await readFile(path.join(profile, "DevToolsActivePort"), "utf8")).split("\n")[0]; }
    catch { await sleep(100); }
  }
  const targets = await (await fetch(`http://127.0.0.1:${port}/json`)).json();
  const page = targets.find((t) => t.type === "page");
  const ws = new WebSocket(page.webSocketDebuggerUrl);
  await new Promise((r) => ws.addEventListener("open", r, { once: true }));
  let id = 0;
  const pending = new Map();
  ws.addEventListener("message", (ev) => {
    const msg = JSON.parse(ev.data);
    if (msg.id && pending.has(msg.id)) { pending.get(msg.id)(msg); pending.delete(msg.id); }
  });
  const send = (method, params = {}) => new Promise((resolve, reject) => {
    const n = ++id; pending.set(n, (m) => (m.error ? reject(new Error(m.error.message)) : resolve(m.result)));
    ws.send(JSON.stringify({ id: n, method, params }));
  });
  const close = async () => { ws.close(); proc.kill(); await sleep(300); await rm(profile, { recursive: true, force: true }); };
  return { send, close };
}

const HELPERS = `
window.__b = {
  set(el, value) {
    const proto = el instanceof HTMLTextAreaElement ? HTMLTextAreaElement.prototype
      : el instanceof HTMLSelectElement ? HTMLSelectElement.prototype : HTMLInputElement.prototype;
    Object.getOwnPropertyDescriptor(proto, "value").set.call(el, value);
    el.dispatchEvent(new Event("input", { bubbles: true }));
    el.dispatchEvent(new Event("change", { bubbles: true }));
  },
  byPlaceholder(p, n = 0) { return [...document.querySelectorAll("[placeholder='" + p + "']")][n]; },
  inLabel(text, tag) { const l = [...document.querySelectorAll("label")].find((x) => x.textContent.includes(text)); return l && l.querySelector(tag); },
  button(text) { return [...document.querySelectorAll("button")].find((b) => b.textContent.trim().startsWith(text) && !b.disabled); },
  pick(n, text) {
    const box = [...document.querySelectorAll("div.max-h-40")][n];
    const l = box && [...box.querySelectorAll("label")].find((x) => x.textContent.includes(text));
    const c = l && l.querySelector("input"); if (c && !c.checked) c.click(); return !!c;
  },
  selectNth(optionValue, n, value) {
    const s = [...document.querySelectorAll("select")].filter((x) => [...x.options].some((o) => o.value === optionValue))[n];
    if (s) this.set(s, value); return !!s;
  },
};`;

async function main() {
  await mkdir(OUT, { recursive: true });
  const { send, close } = await launch();
  const evalJs = async (expr) => {
    const r = await send("Runtime.evaluate", { expression: expr, awaitPromise: true, returnByValue: true });
    if (r.exceptionDetails) throw new Error(r.exceptionDetails.text + " :: " + expr.slice(0, 120));
    return r.result.value;
  };
  const text = () => evalJs("document.body.innerText");
  const waitText = async (needle, ms = 15000) => {
    const end = Date.now() + ms;
    while (Date.now() < end) { if ((await text()).includes(needle)) return; await sleep(200); }
    await shot("falha-" + needle.slice(0, 20).replace(/\W+/g, "_"));
    throw new Error(`texto não apareceu: ${needle}`);
  };
  const shot = async (name) => {
    const { data } = await send("Page.captureScreenshot", { format: "png" });
    await writeFile(path.join(OUT, `${name}.png`), Buffer.from(data, "base64"));
  };
  const as = async (userId, role, route) => {
    await send("Network.setCookie", { name: "basho_persona", value: encodeURIComponent(`${userId}:${role}`), url: BASE });
    await send("Page.navigate", { url: `${BASE}${route}` });
    await sleep(800);
    await evalJs(HELPERS);
  };
  const click = async (label) => assert.ok(await evalJs(`(() => { const b = __b.button(${JSON.stringify(label)}); if (b) b.click(); return !!b; })()`), `botão ${label}`);
  await send("Page.enable"); await send("Network.enable"); await send("Runtime.enable");

  // 1) Ana abre a tela: o rascunho já foi preparado pelo sistema (leitura primeiro)
  await as(ANA, "researcher", "/pesquisador");
  await waitText("rascunho preparado automaticamente pelo sistema");
  await waitText("Checks determinísticos");
  assert.ok(!(await text()).includes("Construir relatório do período"), "não deve pedir que o usuário monte o relatório");
  assert.ok(!(await text()).includes("Registrar evidência"), "registro manual fica escondido");
  await shot("01-ana-rascunho-automatico");

  // 2) Ana nota que falta o resultado negativo: modo edição discreto → v2
  await click("Algo errado? Editar");
  await evalJs(`__b.selectNth("add_experiment", 0, "add_experiment")`);
  await evalJs(`__b.set(__b.byPlaceholder("Descrição do experimento", 0), "Quantização int8 dinâmica no modelo embarcado.")`);
  await evalJs(`__b.selectNth("negative", 0, "negative")`);
  assert.ok(await evalJs(`__b.pick(0, "c94ab")`), "evidência do experimento");
  await evalJs(`__b.set(__b.byPlaceholder("Motivo da correção (obrigatório)", 0), "Faltava registrar a queda de precisão como resultado negativo.")`);
  await shot("02-ana-editando");
  await click("Gerar nova versão");
  await waitText("versão atual v2");
  await waitText("Negativo");
  await shot("03-ana-v2");

  // 3) confirmar a v1 antiga → 409; abrir a atual e confirmar a v2
  await click("v1");
  await waitText("Você está vendo uma versão anterior");
  await click("Confirmar v1");
  await waitText("Conflito de versão (409)");
  await shot("04-conflito-409");
  await click("Abrir a versão atual");
  await waitText("Confirmar v2");
  await click("Confirmar v2");
  await waitText("Texto da v2 confirmado");

  // 4) coordenação registra as horas formais da Ana; Ana resolve a lacuna citando-as (v3)
  await as(CARLA, "manager", "/gerente");
  await click("registrar horas formais de um pesquisador");
  await waitText("Registrar horas formais");
  await evalJs(`__b.set(__b.byPlaceholder("horas", 0), "96")`);
  await evalJs(`__b.set(__b.byPlaceholder("Base do registro (ex.: folha de ponto conferida)", 0), "Folha de ponto de outubro conferida pela coordenação (sintético).")`);
  await click("Registrar");
  await waitText("Registro gravado no ledger");
  await as(ANA, "researcher", "/pesquisador");
  await waitText("Confirmar v2");
  await click("Algo errado? Editar");
  await evalJs(`__b.selectNth("resolve_missing", 0, "resolve_missing")`);
  await evalJs(`(() => { const s = [...document.querySelectorAll("select")].find((x) => [...x.options].some((o) => o.text.startsWith("formal_hours"))); const o = [...s.options].find((o) => o.text.startsWith("formal_hours")); __b.set(s, o.value); })()`);
  await sleep(300);
  assert.ok(await evalJs(`__b.pick(0, "Horas formais — Ana")`), "registro formal de horas");
  await evalJs(`__b.set(__b.byPlaceholder("Motivo da correção (obrigatório)", 0), "Lacuna de horas resolvida pelo registro formal da coordenação.")`);
  await click("Gerar nova versão");
  await waitText("versão atual v3");
  await click("Confirmar v3");
  await waitText("Texto da v3 confirmado");
  await shot("06-ana-v3-confirmada");

  // 5) Bia confirma o próprio relatório (seed)
  await as(BIA, "researcher", "/pesquisador");
  await waitText("Confirmar v1");
  await click("Confirmar v1");
  await waitText("Texto da v1 confirmado");

  // 6) Carla consolida
  await as(CARLA, "manager", "/gerente");
  await waitText("todos os textos confirmados");
  const manager = await text();
  assert.match(manager, /Negativos: 1/);
  assert.match(manager, /Inconclusivos: 1/);
  await shot("07-gerente-consolidacao");
  await click("Aceitar v3");
  await waitText("Gerente: Texto confirmado");

  // 7) Davi consulta o dossiê
  await as(DAVI, "fiscal", "/fiscal");
  await waitText("Itens e evidências (origem verificável)");
  const fiscal = await text();
  assert.match(fiscal, /Resultado negativo/);
  assert.match(fiscal, /Resultado inconclusivo/);
  assert.match(fiscal, /Conflitante/);
  assert.match(fiscal, /report:[0-9a-f-]{36}\/experiment\//);
  assert.doesNotMatch(fiscal, /Ana \(fictícia\)[^\n]*\n[^\n]*\n[^\n]*sem registro formal/);
  await shot("08-fiscal-dossie");

  // 8) viewport estreito
  await send("Emulation.setDeviceMetricsOverride", { width: 390, height: 844, deviceScaleFactor: 1, mobile: true });
  await as(ANA, "researcher", "/pesquisador");
  await waitText("versão atual v3");
  const overflow = await evalJs("document.documentElement.scrollWidth > window.innerWidth + 1");
  await shot("09-mobile-pesquisador");
  await close();
  console.log(JSON.stringify({ ok: true, horizontalOverflowOnMobile: overflow, screenshots: OUT }));
}

main().catch((e) => { console.error(e); process.exit(1); });
