import { randomBytes, scryptSync } from "node:crypto";
import { readFile, writeFile } from "node:fs/promises";

const password = process.env.BASHO_DEMO_PASSWORD;
if (!password || password.length < 12 || password.length > 256) throw new Error("Defina BASHO_DEMO_PASSWORD com 12 a 256 caracteres.");
let previous = "";
try { previous = await readFile(".env.local", "utf8"); } catch (error) { if (error.code !== "ENOENT") throw error; }
if (/^BASHO_DEMO_(?:LOGIN_ENABLED|PASSWORD_HASH)=/m.test(previous)) throw new Error("Configuração já existente; não será sobrescrita.");
const salt = randomBytes(16).toString("hex");
const hash = scryptSync(password, salt, 64).toString("hex");
await writeFile(".env.local", previous + "\nBASHO_DEMO_LOGIN_ENABLED=true\nBASHO_DEMO_PASSWORD_HASH=scrypt:" + salt + ":" + hash + "\n", { mode: 0o600 });
process.stdout.write("Login local configurado. Reinicie o servidor do frontend.\n");
