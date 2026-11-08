import { expect, test } from "vitest";
import { boundedJson } from "../http";

test("limite considera bytes UTF-8 durante a leitura sem Content-Length", async () => {
  const request = new Request("http://localhost/", { method: "POST", body: JSON.stringify({ text: "á".repeat(100) }) });
  const result = await boundedJson(request, 150);
  expect(result).toBeInstanceOf(Response);
  expect((result as Response).status).toBe(413);
});

test("corpo JSON válido é lido e corpo inválido é recusado", async () => {
  expect(await boundedJson(new Request("http://localhost/", { method: "POST", body: '{"ok":true}' }), 100)).toEqual({ ok: true });
  const invalid = await boundedJson(new Request("http://localhost/", { method: "POST", body: "{" }), 100);
  expect((invalid as Response).status).toBe(400);
});

test("Content-Length acima do teto é recusado antes de ler", async () => {
  const request = new Request("http://localhost/", { method: "POST", headers: { "Content-Length": "99999" }, body: "{}" });
  expect((await boundedJson(request, 100) as Response).status).toBe(413);
});
