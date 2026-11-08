/**
 * Links colados na demonstração (GitHub, Drive, Notion): só extrai o identificador, nunca abre a
 * URL. Mesmas regras do backend (`basho.publishing.links`): https, sem credenciais, host em
 * allowlist e formato do ID. Nada aqui acessa serviço externo.
 */

export type SourceKind = "github" | "drive" | "notion";

export interface ParsedSource {
  kind: SourceKind;
  /** `dono/repo`, ID da pasta (Drive) ou ID da página (Notion, 32 hex). */
  id: string;
  /** Nome legível para a tela. */
  label: string;
}

const MAX_URL_LENGTH = 2048;
const DRIVE_ID = /^[A-Za-z0-9_-]{10,128}$/;
const DRIVE_FOLDER_PATH = /^\/drive\/(?:u\/\d+\/)?folders\/([A-Za-z0-9_-]+)\/?$/;
const NOTION_ID = /(?:^|[-/])([0-9a-fA-F]{32})$/;
const GITHUB_PART = /^[A-Za-z0-9_.-]+$/;

export const SOURCE_LABEL: Record<SourceKind, string> = {
  github: "Repositório do GitHub",
  drive: "Pasta do Google Drive",
  notion: "Página do Notion",
};

export const SOURCE_HINT: Record<SourceKind, string> = {
  github: "https://github.com/dono/repositorio",
  drive: "https://drive.google.com/drive/folders/<id-da-pasta>",
  notion: "https://www.notion.so/Titulo-<32 caracteres hex>",
};

/** Exemplos hipotéticos válidos, para a demonstração. */
export const EXAMPLE_LINKS: Record<SourceKind, string> = {
  github: "https://github.com/equipe-basho/calibracao-sensores",
  drive: "https://drive.google.com/drive/folders/1AbCdEfGhIjKlMnOpQrStUvWxYz012345",
  notion: "https://www.notion.so/Diario-de-bancada-0123456789abcdef0123456789abcdef",
};

export class InvalidSourceLink extends Error {}

function splitUrl(raw: string): URL {
  const text = raw.trim();
  if (text.length > MAX_URL_LENGTH) throw new InvalidSourceLink("O link é longo demais.");
  let url: URL;
  try {
    url = new URL(text);
  } catch {
    throw new InvalidSourceLink("Cole um link https completo.");
  }
  if (url.protocol !== "https:") throw new InvalidSourceLink("Use um link https completo.");
  if (url.username || url.password || (url.port !== "" && url.port !== "443")) {
    throw new InvalidSourceLink("Link com credenciais ou porta não é aceito.");
  }
  return url;
}

function parseGithub(url: URL): ParsedSource {
  const [owner, rawName] = url.pathname.split("/").filter(Boolean);
  const name = rawName?.replace(/\.git$/, "");
  if (!owner || !name) throw new InvalidSourceLink("Cole o link de um repositório: github.com/dono/nome.");
  if (!GITHUB_PART.test(owner) || !GITHUB_PART.test(name) || /^\.+$/.test(name)) {
    throw new InvalidSourceLink("Repositório inválido.");
  }
  return { kind: "github", id: `${owner}/${name}`, label: `${owner}/${name}` };
}

function parseDrive(url: URL): ParsedSource {
  const match = DRIVE_FOLDER_PATH.exec(url.pathname);
  const id = match?.[1] ?? url.searchParams.get("id") ?? "";
  if (!DRIVE_ID.test(id)) throw new InvalidSourceLink("Não achei o ID da pasta. Cole o link de uma pasta do Google Drive.");
  return { kind: "drive", id, label: `Pasta do Drive …${id.slice(-6)}` };
}

function parseNotion(url: URL): ParsedSource {
  const last = url.pathname.split("/").filter(Boolean).at(-1) ?? "";
  const match = NOTION_ID.exec(last);
  if (!match) throw new InvalidSourceLink("Não achei o ID da página. Cole o link de uma página do Notion.");
  const id = match[1].toLowerCase();
  const title = last.slice(0, last.length - id.length).replace(/-+$/, "").replace(/-/g, " ").trim();
  return { kind: "notion", id, label: title ? `Notion · ${title}` : `Notion …${id.slice(-6)}` };
}

/** Valida o link para o tipo esperado e devolve só o identificador. */
export function parseSourceLink(kind: SourceKind, raw: string): ParsedSource {
  const url = splitUrl(raw);
  const host = url.hostname.toLowerCase();
  if (kind === "github") {
    if (host !== "github.com" && host !== "www.github.com") throw new InvalidSourceLink("Esse link não é do GitHub.");
    return parseGithub(url);
  }
  if (kind === "drive") {
    if (host !== "drive.google.com") throw new InvalidSourceLink("Esse link não é do Google Drive.");
    return parseDrive(url);
  }
  if (host !== "notion.so" && !host.endsWith(".notion.so") && !host.endsWith(".notion.site")) {
    throw new InvalidSourceLink("Esse link não é do Notion.");
  }
  return parseNotion(url);
}
