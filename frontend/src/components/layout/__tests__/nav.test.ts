import { describe, expect, test } from "vitest";
import { activeItem, isActive, NAV_ITEMS } from "@/components/layout/nav";

const activeHrefs = (pathname: string) => NAV_ITEMS.filter(item => isActive(item, pathname)).map(item => item.href);

describe("sidebar: um único item ativo", () => {
  test.each([
    ["/", ["/"]],
    ["/pesquisador", ["/pesquisador"]],
    ["/pesquisador/pendencias", ["/pesquisador"]],
    ["/pesquisador/fontes", ["/pesquisador/fontes"]],
    ["/gerente", ["/gerente"]],
    ["/gerente/pendencias", ["/gerente"]],
    ["/gerente/dossie", ["/gerente"]],
    ["/gerente/publicacao", ["/gerente/publicacao"]],
    ["/fiscal", ["/fiscal"]],
    ["/integracoes", ["/integracoes"]],
  ])("%s ativa %j", (pathname, expected) => {
    expect(activeHrefs(pathname)).toEqual(expected);
  });

  test("não casa por prefixo parcial de segmento", () => {
    expect(activeHrefs("/gerente-externo")).toEqual([]);
  });

  test("activeItem concorda com isActive", () => {
    expect(activeItem("/gerente/publicacao")?.href).toBe("/gerente/publicacao");
    expect(activeItem(null)).toBeUndefined();
  });
});
