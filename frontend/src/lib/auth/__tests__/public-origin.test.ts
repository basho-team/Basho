import { describe, expect, test } from "vitest";

import { publicOrigin, sameOriginJson } from "../session";

const behindProxy = (origin: string) => new Request("http://10.0.0.5:8080/api/auth/login", {
  method: "POST",
  headers: {
    "content-type": "application/json",
    origin,
    host: "10.0.0.5:8080",
    "x-forwarded-host": "basho.example",
    "x-forwarded-proto": "https",
  },
});

describe("origem atrás de proxy (Railway)", () => {
  test("aceita a origem pública informada pela borda", () => {
    expect(publicOrigin(behindProxy("https://basho.example"))).toBe("https://basho.example");
    expect(sameOriginJson(behindProxy("https://basho.example"))).toBe(true);
  });

  test("recusa outra origem e o endereço interno", () => {
    expect(sameOriginJson(behindProxy("https://evil.test"))).toBe(false);
    expect(sameOriginJson(behindProxy("http://10.0.0.5:8080"))).toBe(false);
  });

  test("sem headers de proxy, usa a própria URL", () => {
    expect(publicOrigin(new Request("http://localhost:3002/x"))).toBe("http://localhost:3002");
  });
});
