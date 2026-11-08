import "server-only";
import { authError } from "./session";

/** Limite aplicado durante a leitura: não carrega um corpo arbitrário inteiro em memória. */
export async function boundedJson(request: Request, maxBytes: number): Promise<unknown | Response> {
  const declared = request.headers.get("content-length");
  if (declared !== null && (!/^\d+$/.test(declared) || Number(declared) > maxBytes)) {
    return authError(413, "Solicitação muito grande.");
  }
  const reader = request.body?.getReader();
  if (!reader) return authError(400, "Solicitação inválida.");
  const chunks: Uint8Array[] = [];
  let length = 0;
  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      length += value.byteLength;
      if (length > maxBytes) {
        await reader.cancel();
        return authError(413, "Solicitação muito grande.");
      }
      chunks.push(value);
    }
    const buffer = new Uint8Array(length);
    let offset = 0;
    for (const chunk of chunks) { buffer.set(chunk, offset); offset += chunk.byteLength; }
    return JSON.parse(new TextDecoder().decode(buffer)) as unknown;
  } catch {
    return authError(400, "Solicitação inválida.");
  } finally { reader.releaseLock(); }
}
