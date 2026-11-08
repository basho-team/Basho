import { describe, expect, test } from "vitest";
import { BffLinkRequestSchema, isSafeExternalUrl } from "@/lib/bff/integrations-contract";

describe("isSafeExternalUrl", () => {
  test.each([
    "https://docs.google.com/document/d/abc/edit",
    "https://drive.google.com/file/d/abc/view",
    "https://www.notion.so/BASHO-0123456789abcdef0123456789abcdef",
    "https://time.notion.site/Relatorio-0123456789abcdef0123456789abcdef",
  ])("aceita %s", (url) => {
    expect(isSafeExternalUrl(url)).toBe(true);
  });

  test.each([
    null,
    "",
    "javascript:alert(1)",
    "data:text/html,<script>alert(1)</script>",
    "http://docs.google.com/document/d/abc",
    "https://docs.google.com.evil.example/x",
    "https://evil.example/notion.so",
    "//docs.google.com/x",
    "não é url",
  ])("recusa %s", (url) => {
    expect(isSafeExternalUrl(url)).toBe(false);
  });
});

describe("BffLinkRequestSchema", () => {
  test("recorta espaços e exige tamanho razoável", () => {
    expect(BffLinkRequestSchema.parse({ url: "  https://github.com/a/b  " }).url).toBe("https://github.com/a/b");
    expect(BffLinkRequestSchema.safeParse({ url: "a" }).success).toBe(false);
    expect(BffLinkRequestSchema.safeParse({ url: "https://x.example/" + "a".repeat(3000) }).success).toBe(false);
    expect(BffLinkRequestSchema.safeParse({ url: "https://github.com/a/b", extra: true }).success).toBe(false);
  });
});
