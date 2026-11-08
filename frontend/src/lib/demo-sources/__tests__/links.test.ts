import { describe, expect, test } from "vitest";
import { EXAMPLE_LINKS, InvalidSourceLink, parseSourceLink, type SourceKind } from "@/lib/demo-sources/links";

const DRIVE_ID = "1AbCdEfGhIjKlMnOpQrStUvWxYz012345";
const NOTION_ID = "0123456789abcdef0123456789abcdef";

describe("links de demonstração", () => {
  test.each(["github", "drive", "notion"] as const)("o exemplo de %s é válido", kind => {
    expect(parseSourceLink(kind, EXAMPLE_LINKS[kind]).kind).toBe(kind);
  });

  test.each([
    ["https://github.com/equipe/projeto", "equipe/projeto"],
    ["https://github.com/equipe/projeto.git", "equipe/projeto"],
    ["https://www.github.com/equipe/projeto/pull/3", "equipe/projeto"],
    ["  https://github.com/a/b  ", "a/b"],
  ])("GitHub %s → %s", (url, id) => {
    expect(parseSourceLink("github", url).id).toBe(id);
  });

  test.each([
    `https://drive.google.com/drive/folders/${DRIVE_ID}?usp=sharing`,
    `https://drive.google.com/drive/u/1/folders/${DRIVE_ID}`,
    `https://drive.google.com/open?id=${DRIVE_ID}`,
  ])("Drive %s → ID da pasta", url => {
    expect(parseSourceLink("drive", url).id).toBe(DRIVE_ID);
  });

  test.each([
    `https://www.notion.so/Meu-Projeto-${NOTION_ID}`,
    `https://www.notion.so/espaco/Meu-Projeto-${NOTION_ID}?pvs=4`,
    `https://time.notion.site/Diario-${NOTION_ID}`,
  ])("Notion %s → ID da página", url => {
    expect(parseSourceLink("notion", url).id).toBe(NOTION_ID);
  });

  test.each<[SourceKind, string]>([
    ["github", ""],
    ["github", "não é link"],
    ["github", "http://github.com/a/b"],
    ["github", "https://user:senha@github.com/a/b"],
    ["github", "https://github.com:8443/a/b"],
    ["github", "https://github.com/so-o-dono"],
    ["github", "https://github.com/a/.."],
    ["github", "https://evil.example/a/b"],
    ["github", "https://github.com.evil.example/a/b"],
    ["drive", "https://169.254.169.254/latest/meta-data/"],
    ["drive", "https://localhost:8000/drive/folders/" + DRIVE_ID],
    ["drive", "https://drive.google.com/drive/my-drive"],
    ["drive", "https://drive.google.com/drive/folders/curto"],
    ["drive", "https://evil.example/drive/folders/" + DRIVE_ID],
    ["notion", "https://www.notion.so/sem-id-aqui"],
    ["notion", "https://evil.example/" + NOTION_ID],
    ["notion", "javascript:alert(1)"],
    ["drive", "https://drive.google.com/drive/folders/" + "A".repeat(3000)],
  ])("recusa %s: %s", (kind, url) => {
    expect(() => parseSourceLink(kind, url)).toThrow(InvalidSourceLink);
  });

  test("um link do tipo errado é recusado (Drive no campo do GitHub)", () => {
    expect(() => parseSourceLink("github", EXAMPLE_LINKS.drive)).toThrow(InvalidSourceLink);
    expect(() => parseSourceLink("notion", EXAMPLE_LINKS.github)).toThrow(InvalidSourceLink);
  });
});
