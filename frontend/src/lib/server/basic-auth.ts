/** Verificação de Basic Auth do deploy de demonstração (usada pelo `src/proxy.ts`). */

export type BasicAuthResult = "allow" | "deny" | "misconfigured";

export type BasicAuthConfig = {
  readonly dataSource: string | undefined;
  readonly user: string | undefined;
  readonly password: string | undefined;
};

const BASIC_PREFIX = "Basic ";

/** Comparação sem atalho por posição (evita vazar o prefixo correto pelo tempo de resposta). */
function safeEqual(a: string, b: string): boolean {
  const length = Math.max(a.length, b.length);
  let diff = a.length ^ b.length;
  for (let i = 0; i < length; i += 1) {
    diff |= (a.charCodeAt(i) || 0) ^ (b.charCodeAt(i) || 0);
  }
  return diff === 0;
}

function decodeCredentials(header: string): { user: string; password: string } | null {
  if (!header.startsWith(BASIC_PREFIX)) return null;
  let decoded: string;
  try {
    decoded = atob(header.slice(BASIC_PREFIX.length).trim());
  } catch {
    return null;
  }
  const separator = decoded.indexOf(":");
  if (separator < 0) return null;
  return { user: decoded.slice(0, separator), password: decoded.slice(separator + 1) };
}

/**
 * Sem credenciais configuradas: modo `mock` fica aberto (só dados sintéticos estáticos);
 * qualquer outro modo fica fechado ("misconfigured").
 */
export function checkBasicAuth(header: string | null, config: BasicAuthConfig): BasicAuthResult {
  const { user, password } = config;
  if (!user || !password) {
    return (config.dataSource ?? "mock") === "mock" ? "allow" : "misconfigured";
  }
  const credentials = header ? decodeCredentials(header) : null;
  if (!credentials) return "deny";
  const userOk = safeEqual(credentials.user, user);
  const passwordOk = safeEqual(credentials.password, password);
  return userOk && passwordOk ? "allow" : "deny";
}
