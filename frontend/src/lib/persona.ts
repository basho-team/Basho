/** Persona da demonstração. NÃO é autenticação: só escolhe em nome de quem o BFF age. */
export const PERSONA_COOKIE = "basho_persona";
export const ROLES = ["researcher", "manager", "fiscal"] as const;
export type Role = (typeof ROLES)[number];

export interface Persona {
  userId: string;
  role: Role;
}

const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

export function parsePersona(raw: string | undefined | null): Persona | null {
  if (!raw) return null;
  const [userId, role] = decodeURIComponent(raw).split(":");
  if (!userId || !UUID_RE.test(userId)) return null;
  if (!ROLES.includes(role as Role)) return null;
  return { userId, role: role as Role };
}

export function serializePersona(persona: Persona): string {
  return encodeURIComponent(`${persona.userId}:${persona.role}`);
}
