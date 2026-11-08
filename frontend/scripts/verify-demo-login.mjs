import assert from "node:assert/strict";

const base = process.env.BASHO_DEMO_TEST_URL ?? "http://localhost:3002";
const password = process.env.BASHO_DEMO_TEST_PASSWORD;
if (!password) throw new Error("Defina BASHO_DEMO_TEST_PASSWORD para testar as contas locais.");
const results = [];
const accounts = [
  { email: "ana@lumen.example", role: "researcher", person: "p-ana", home: "/pesquisador" },
  { email: "bruno@lumen.example", role: "researcher", person: "p-bruno", home: "/pesquisador" },
  { email: "marina@lumen.example", role: "manager", person: "p-marina", home: "/gerente" },
  { email: "rafael@lumen.example", role: "fiscal", person: "p-rafael", home: "/fiscal" },
];
async function request(path, { cookie, body, origin = base, headers = {}, method = body ? "POST" : "GET" } = {}) {
  return fetch(base + path, { method, redirect: "manual", headers: {
    ...(cookie ? { Cookie: cookie } : {}), ...(body ? { "Content-Type": "application/json", Origin: origin } : {}), ...headers,
  }, body: body ? JSON.stringify(body) : undefined });
}
async function operation(cookie, name, args, expected = 200, headers) {
  const response = await request("/api/demo", { cookie, body: { operation: name, args }, headers });
  assert.equal(response.status, expected, name + ": status inesperado");
  return response.json();
}
assert.equal((await request("/pesquisador")).status, 307);
assert.equal((await request("/api/integrations")).status, 401);
assert.equal((await request("/api/demo", { body: { operation: "getContext", args: [] } })).status, 401);
assert.equal((await request("/api/auth/login", { body: { email: accounts[0].email, password: "wrong", role: "researcher" } })).status, 401);
assert.equal((await request("/api/auth/login", { body: { email: accounts[0].email, password, role: "manager" } })).status, 401);
assert.equal((await request("/api/auth/login", { origin: "http://evil.test", body: { email: accounts[0].email, password, role: "researcher" } })).status, 403);
results.push("acesso anônimo, senha incorreta, função indevida e CSRF bloqueados");
const sessions = [];
for (const account of accounts) {
  const login = await request("/api/auth/login", { body: { email: account.email, password, role: account.role } });
  assert.equal(login.status, 200, "login da conta de demonstração");
  const setCookie = login.headers.get("set-cookie");
  assert.match(setCookie, /HttpOnly/i); assert.match(setCookie, /SameSite=lax/i);
  const cookie = setCookie.split(";")[0];
  sessions.push({ ...account, cookie });
  const session = await (await request("/api/auth/session", { cookie })).json();
  assert.equal(session.user.role, account.role); assert.equal(session.user.personId, account.person);
  assert.equal((await request(account.home, { cookie })).status, 200);
  const denied = account.role === "manager" ? "/fiscal" : "/gerente";
  const blocked = await request(denied, { cookie });
  assert.equal(blocked.status, 307); assert.match(blocked.headers.get("location"), /acesso-negado/);
  const previews = await (await request("/api/integrations", { cookie })).json();
  assert.equal(previews.integrations.length, 3);
  for (const provider of ["github", "notion", "drive"]) {
    const verified = await request("/api/integrations", { cookie, body: { provider, action: "verify" } });
    assert.equal(verified.status, 200);
    const integration = (await verified.json()).integrations.find(item => item.provider === provider);
    assert.ok(integration.sources.length > 0);
    assert.ok(integration.sources.every(source => source.isSynthetic));
    if (account.role === "researcher") assert.ok(integration.sources.every(source => source.ownerId === account.person));
    if (account.role !== "manager") {
      assert.equal((await request("/api/integrations", { cookie, body: { provider, action: "disable" } })).status, 403);
    }
  }
  if (account.role === "researcher") {
    const reports = await operation(cookie, "listReports", ["per-2026-10"]);
    assert.ok(reports.length > 0 && reports.every(report => report.author_id === account.person));
    const other = account.person === "p-ana" ? "rep-bruno" : "rep-ana";
    await operation(cookie, "getReport", [other, null], 403);
    await operation(cookie, "triggerClosing", ["per-2026-10"], 403, { "X-Demo-Role": "manager" });
  } else if (account.role === "fiscal") {
    await operation(cookie, "getFiscalPackage", ["per-2026-10"]);
    await operation(cookie, "triggerClosing", ["per-2026-10"], 403);
  } else {
    await operation(cookie, "getConsolidation", ["per-2026-10"]);
  }
  results.push(account.role + "/" + account.person + ": tela própria, bloqueios e três prévias verificados");
}
const researcher = sessions[0].cookie;
const manager = sessions[2].cookie;
assert.equal((await request("/api/integrations", { cookie: manager, body: { provider: "drive", action: "disable" } })).status, 200);
assert.equal((await request("/api/integrations", { cookie: researcher, body: { provider: "drive", action: "verify" } })).status, 409);
assert.equal((await request("/api/integrations", { cookie: manager, body: { provider: "drive", action: "enable" } })).status, 200);
for (const account of sessions) {
  assert.equal((await request("/api/auth/logout", { cookie: account.cookie, body: {} })).status, 200);
  assert.equal((await request("/api/auth/session", { cookie: account.cookie })).status, 401);
  assert.equal((await request(account.home, { cookie: account.cookie })).status, 307);
}
results.push("configuração compartilhada, logout e repetição de cookie revogado verificados");
process.stdout.write(JSON.stringify({ passed: results.length, results }, null, 2) + "\n");
