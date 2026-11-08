import { describe, expect, it } from "vitest";

import { checkBasicAuth } from "../basic-auth";

const configured = { dataSource: "api", user: "juri", password: "senha-forte" };
const header = (value: string) => `Basic ${btoa(value)}`;

describe("checkBasicAuth", () => {
  it("permite credenciais corretas", () => {
    expect(checkBasicAuth(header("juri:senha-forte"), configured)).toBe("allow");
  });

  it("aceita senha contendo dois-pontos", () => {
    const config = { ...configured, password: "a:b" };
    expect(checkBasicAuth(header("juri:a:b"), config)).toBe("allow");
  });

  it("nega senha errada, usuário errado e header ausente ou malformado", () => {
    expect(checkBasicAuth(header("juri:errada"), configured)).toBe("deny");
    expect(checkBasicAuth(header("outro:senha-forte"), configured)).toBe("deny");
    expect(checkBasicAuth(null, configured)).toBe("deny");
    expect(checkBasicAuth("Bearer x", configured)).toBe("deny");
    expect(checkBasicAuth("Basic %%%", configured)).toBe("deny");
  });

  it("fecha o modo api quando as credenciais não estão configuradas", () => {
    const config = { dataSource: "api", user: undefined, password: undefined };
    expect(checkBasicAuth(null, config)).toBe("misconfigured");
  });

  it("deixa o modo mock aberto quando não há credenciais", () => {
    const config = { dataSource: "mock", user: "", password: undefined };
    expect(checkBasicAuth(null, config)).toBe("allow");
    expect(checkBasicAuth(null, { ...config, dataSource: undefined })).toBe("allow");
  });
});
