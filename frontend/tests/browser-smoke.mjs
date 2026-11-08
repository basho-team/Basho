import { spawn } from "node:child_process";
import { mkdir, readFile, writeFile, access } from "node:fs/promises";
import path from "node:path";
import assert from "node:assert/strict";

// Browser QA uses an isolated headless Edge profile and localhost only.
// Start `npm run start` before running this script. No browser dependency is downloaded.
const base = process.env.BASHO_QA_URL ?? "http://127.0.0.1:3000";
const binary =
  process.env.BASHO_QA_BROWSER ??
  "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe";
const artifacts = path.resolve(".qa");
const profile = path.join(artifacts, `profile-${process.pid}`);
await access(binary);
await mkdir(profile, { recursive: true });
const browser = spawn(
  binary,
  [
    "--headless=new",
    "--disable-gpu",
    "--no-first-run",
    "--disable-default-apps",
    "--disable-extensions",
    "--disable-background-networking",
    "--remote-debugging-address=127.0.0.1",
    "--remote-debugging-port=0",
    `--user-data-dir=${profile}`,
    "about:blank",
  ],
  { windowsHide: true, stdio: "ignore" },
);
const pause = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
let socket;
const pending = new Map(),
  exceptions = [];
let sequence = 0;
function rpc(method, params = {}) {
  return new Promise((resolve, reject) => {
    const id = ++sequence;
    const timeout = setTimeout(() => {
      pending.delete(id);
      reject(new Error(`CDP timeout: ${method}`));
    }, 15000);
    pending.set(id, {
      resolve: (value) => {
        clearTimeout(timeout);
        resolve(value);
      },
      reject,
    });
    socket.send(JSON.stringify({ id, method, params }));
  });
}
async function evaluate(expression) {
  const response = await rpc("Runtime.evaluate", {
    expression,
    awaitPromise: true,
    returnByValue: true,
  });
  if (response.exceptionDetails)
    throw new Error(
      response.exceptionDetails.text +
        ": " +
        response.exceptionDetails.exception?.description,
    );
  return response.result?.value;
}
async function waitFor(expression, timeout = 15000) {
  const start = Date.now();
  while (Date.now() - start < timeout) {
    try {
      if (await evaluate(expression)) return;
    } catch (error) {
      if (!/context|navigation/i.test(error.message)) throw error;
    }
    await pause(100);
  }
  throw new Error(`UI condition timed out: ${expression}`);
}
async function go(route) {
  await rpc("Page.navigate", { url: base + route });
  await waitFor(
    `document.readyState==='complete' && !!document.querySelector('main h2')`,
  );
}
async function click(text) {
  await evaluate(
    `(()=>{const button=[...document.querySelectorAll('button')].find(b=>b.textContent.trim()===${JSON.stringify(text)});if(!button)throw Error('Button not found: '+${JSON.stringify(text)});if(button.disabled)throw Error('Button disabled');button.click();})()`,
  );
  await pause(80);
}
async function fill(selector, value) {
  await evaluate(
    `(()=>{const el=document.querySelector(${JSON.stringify(selector)});if(!el)throw Error('Field not found');const proto=el.tagName==='TEXTAREA'?HTMLTextAreaElement.prototype:el.tagName==='SELECT'?HTMLSelectElement.prototype:HTMLInputElement.prototype;Object.getOwnPropertyDescriptor(proto,'value').set.call(el,${JSON.stringify(value)});el.dispatchEvent(new Event(el.tagName==='SELECT'?'change':'input',{bubbles:true}));})()`,
  );
}
async function state() {
  return evaluate(`JSON.parse(localStorage.getItem('basho-demo-v2')).state`);
}
async function settled() {
  await waitFor(
    `!JSON.parse(localStorage.getItem('basho-demo-v2')).state.agentRuns.some(r=>r.status==='running')`,
  );
}
async function shot(name, width = 1440, height = 1000) {
  await rpc("Emulation.setDeviceMetricsOverride", {
    width,
    height,
    deviceScaleFactor: 1,
    mobile: width < 600,
  });
  await pause(150);
  const response = await rpc("Page.captureScreenshot", {
    format: "png",
    captureBeyondViewport: false,
  });
  await writeFile(
    path.join(artifacts, `${name}.png`),
    Buffer.from(response.data, "base64"),
  );
}
function pass(message) {
  process.stdout.write(`PASS ${message}\n`);
}
try {
  let port;
  for (let i = 0; i < 100; i++) {
    try {
      port = Number(
        (
          await readFile(path.join(profile, "DevToolsActivePort"), "utf8")
        ).split("\n")[0],
      );
      break;
    } catch {
      await pause(100);
    }
  }
  if (!port) throw new Error("Headless browser did not start");
  const pages = await fetch(`http://127.0.0.1:${port}/json/list`).then((r) =>
    r.json(),
  );
  socket = new WebSocket(
    pages.find((p) => p.type === "page").webSocketDebuggerUrl,
  );
  await new Promise((resolve, reject) => {
    socket.onopen = resolve;
    socket.onerror = reject;
  });
  socket.onmessage = (event) => {
    const message = JSON.parse(event.data);
    if (message.id) {
      const promise = pending.get(message.id);
      pending.delete(message.id);
      if (message.error) promise?.reject(new Error(message.error.message));
      else promise?.resolve(message.result);
    } else if (message.method === "Runtime.exceptionThrown")
      exceptions.push(message.params.exceptionDetails);
  };
  await rpc("Page.enable");
  await rpc("Runtime.enable");
  await go("/integracoes");
  await click("Simular conexão");
  await click("Simular conexão");
  await click("Instalar App simulada");
  assert.equal(
    (await state()).integrations.filter((i) => i.status === "connected").length,
    3,
  );
  pass("connect all three simulated integrations");
  await shot("integracoes");
  await go("/operacoes");
  await click("Simular PR integrado");
  await settled();
  let snapshot = await state();
  assert.equal(snapshot.agentRuns[0].status, "completed");
  assert.equal(snapshot.evidence.length, 1);
  assert.equal(snapshot.activities[0].status, "review");
  assert.ok(
    snapshot.driveItems.some((d) =>
      d.content?.includes(snapshot.evidence[0].id),
    ),
  );
  pass("workflow A updates activity, evidence and document through UI");
  await click("Simular documento");
  await settled();
  snapshot = await state();
  assert.equal(snapshot.agentRuns[0].status, "completed");
  assert.ok(snapshot.driveItems.some((d) => d.derivedFromId));
  pass("workflow B preserves original and creates work copy");
  await click("Simular exceção");
  await settled();
  assert.equal((await state()).agentRuns[0].status, "awaiting_approval");
  await shot("operacoes");
  await go("/aprovacoes");
  await fill(
    "textarea",
    "Encaminhar para revisão técnica; contexto sintético.",
  );
  await click("Aprovar ação preparada");
  await settled();
  assert.equal((await state()).agentRuns[0].status, "completed");
  pass("workflow C resumes after human approval");
  await go("/documentos");
  await click("Novo arquivo");
  await fill(
    '[role="dialog"] input[name="name"]',
    "Registro criado pelo gestor.md",
  );
  await fill(
    '[role="dialog"] textarea[name="content"]',
    "Conteúdo sintético de teste visual.",
  );
  await click("Salvar alterações");
  snapshot = await state();
  let created = snapshot.driveItems.find(
    (d) => d.name === "Registro criado pelo gestor.md",
  );
  assert.ok(created);
  pass("create document through manager");
  await fill(
    'input[placeholder="Pesquisar em todos os arquivos…"]',
    created.name,
  );
  await evaluate(
    `document.querySelector('button[aria-label="Mover Registro criado pelo gestor.md"]').click()`,
  );
  await fill(
    '[role="dialog"] select[name="destination"]',
    "drive-folder-pd001-agent-work",
  );
  await click("Salvar alterações");
  assert.equal(
    (await state()).driveItems.find((d) => d.id === created.id).parentId,
    "drive-folder-pd001-agent-work",
  );
  await evaluate(
    `document.querySelector('button[aria-label="Renomear Registro criado pelo gestor.md"]').click()`,
  );
  await fill('[role="dialog"] input[name="name"]', "Registro renomeado.md");
  await click("Salvar alterações");
  assert.equal(
    (await state()).driveItems.find((d) => d.id === created.id).name,
    "Registro renomeado.md",
  );
  pass("move and rename document update persisted state");
  await go("/atividades");
  await click("Nova atividade");
  await fill(
    '[role="dialog"] input[name="title"]',
    "Validar hipótese sintética",
  );
  await fill('[role="dialog"] input[name="assignee"]', "Equipe Demo");
  await click("Salvar alterações");
  snapshot = await state();
  const activity = snapshot.activities.find(
    (a) => a.title === "Validar hipótese sintética",
  );
  assert.ok(activity);
  pass("create activity through Notion board");
  await fill(
    `select[aria-label="Status de Validar hipótese sintética"]`,
    "done",
  );
  await waitFor(
    `JSON.parse(localStorage.getItem('basho-demo-v2')).state.approvalRequests.some(a=>a.status==='pending' && a.command?.id===${JSON.stringify(activity.id)})`,
  );
  await go("/aprovacoes");
  await click("Aprovar ação preparada");
  assert.equal(
    (await state()).activities.find((a) => a.id === activity.id).status,
    "done",
  );
  pass("completing a task requires individual approval");
  await go("/integracoes");
  await evaluate(
    `document.querySelector('button[aria-label="Configurar GitHub"]').click()`,
  );
  await click("Simular chegada");
  await settled();
  assert.equal((await state()).agentRuns[0].status, "completed");
  pass("GitHub feed automatically starts workflow A");
  await go("/lei-do-bem");
  const docsBefore = (await state()).driveItems.length;
  await click("Gerar estrutura preliminar");
  assert.equal((await state()).driveItems.length, docsBefore + 1);
  pass("preliminary dossier becomes a document in shared state");
  await go("/autonomia");
  await fill('select[aria-label="Política para Criar documentos"]', "blocked");
  await go("/operacoes");
  await click("Simular PR integrado");
  await settled();
  assert.equal((await state()).agentRuns[0].status, "blocked_by_policy");
  pass("workflow obeys policy configured through UI");
  const saved = await state();
  await go("/");
  assert.deepEqual(
    (await state()).permissionPolicies,
    saved.permissionPolicies,
  );
  await shot("dashboard");
  pass("reload preserves configurations and shared data");
  await shot("mobile", 390, 844);
  await evaluate(
    `document.querySelector('button[aria-label="Abrir navegação"]').click()`,
  );
  await pause(100);
  assert.ok(
    await evaluate(`!!document.querySelector('aside a[href="/integracoes"]')`),
  );
  await evaluate(
    `document.querySelector('button[aria-label="Fechar navegação"]').click()`,
  );
  const overflow = await evaluate(
    `document.documentElement.scrollWidth>window.innerWidth`,
  );
  assert.equal(overflow, false);
  pass("mobile navigation opens and no viewport overflow is present");
  await rpc("Emulation.clearDeviceMetricsOverride");
  for (const route of [
    "/projetos",
    "/projetos/pd-001",
    "/projetos/pd-002",
    "/documentos",
    "/auditoria",
    "/aprovacoes",
  ]) {
    await go(route);
    assert.ok(await evaluate(`!!document.querySelector('main h2')`));
  }
  await click("Restaurar dados");
  await click("Restaurar");
  assert.equal((await state()).agentRuns.length, 0);
  assert.equal(
    (await state()).integrations.filter((i) => i.status === "connected").length,
    0,
  );
  pass("restore replaces all demo data and settings");
  assert.deepEqual(exceptions, []);
  pass("all routes render without browser runtime exceptions");
  process.stdout.write(`Browser QA complete. Screenshots: ${artifacts}\n`);
} finally {
  if (socket?.readyState === WebSocket.OPEN) {
    try {
      await rpc("Browser.close");
    } catch {}
    socket.close();
  }
  browser.kill();
}
