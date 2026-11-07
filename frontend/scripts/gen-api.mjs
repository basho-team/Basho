// Gera tipos TypeScript a partir do OpenAPI do backend (FastAPI).
import { spawnSync } from "node:child_process";

const DEFAULT_OPENAPI_URL = "http://localhost:8000/openapi.json";
const OUTPUT_PATH = "src/lib/api/schema.d.ts";

const source = process.env.OPENAPI_URL ?? DEFAULT_OPENAPI_URL;
const result = spawnSync("openapi-typescript", [source, "-o", OUTPUT_PATH], {
  stdio: "inherit",
  shell: process.platform === "win32",
});

process.exit(result.status ?? 1);
