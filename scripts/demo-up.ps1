<#
.SYNOPSIS
  Sobe a demonstração do Basho no Windows: Postgres, migrações, seed, API e front (modo api).

.DESCRIPTION
  Tudo local e descartável: credenciais de demo, dados sintéticos (is_synthetic). Não use em
  produção. Pré-requisitos: Docker Desktop ligado, uv e Node instalados.
  O worker também sobe: é ele que publica os relatórios no Drive/Notion e roda o agente.
  Publicação real: defina GOOGLE_SERVICE_ACCOUNT_JSON e/ou NOTION_TOKEN antes de rodar.
  -FakeProviders: usa um servidor FALSO de Drive/Notion (scripts/dev/fake_providers.py) para
  ensaiar o fluxo sem credenciais; os documentos abrem no navegador em http://127.0.0.1:9100.
  Para o agente rodar de verdade, veja docs/demo.md (chaves de LLM).

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File scripts/demo-up.ps1
  powershell -ExecutionPolicy Bypass -File scripts/demo-up.ps1 -FakeProviders
  powershell -ExecutionPolicy Bypass -File scripts/demo-up.ps1 -Down
#>
param(
    [int]$DbPort = 55499,
    [int]$ApiPort = 8010,
    [int]$WebPort = 3010,
    [int]$FakePort = 9100,
    [switch]$FakeProviders,
    [switch]$Down
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$container = "basho-demo-pg"
$logs = Join-Path $root ".demo-logs"
$tenant = "11111111-1111-4111-8111-111111111111"
$identitySecret = "demo-secret-with-at-least-32-chars-ok-1"
$researcher = "22222222-2222-4222-8222-222222222222"
$manager = "55555555-5555-4555-8555-555555555555"

function Stop-Port([int]$port) {
    Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue |
        ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }
}

function Stop-Pids {
    $file = Join-Path $logs "worker.pid"
    if (Test-Path $file) {
        # `uv run` é só o lançador: encerra a árvore inteira para não deixar o python órfão.
        Get-Content $file | ForEach-Object { cmd /c "taskkill /PID $([int]$_) /T /F >nul 2>&1" }
        Remove-Item $file -Force
    }
}

if ($Down) {
    Stop-Port $ApiPort; Stop-Port $WebPort; Stop-Port $FakePort; Stop-Pids
    docker rm -f $container | Out-Null
    Write-Host "Demo parada (API, front e Postgres descartável removidos)."
    return
}

New-Item -ItemType Directory -Force $logs | Out-Null

# 1. Postgres descartável
if (-not (docker ps -a --format "{{.Names}}" | Select-String -SimpleMatch $container)) {
    docker run -d --name $container -e POSTGRES_USER=basho -e POSTGRES_PASSWORD=demo_throwaway `
        -e POSTGRES_DB=basho -p "127.0.0.1:${DbPort}:5432" postgres:16-alpine | Out-Null
} else {
    docker start $container | Out-Null
}
for ($i = 0; $i -lt 40; $i++) {
    docker exec $container pg_isready -U basho -d basho *> $null
    if ($LASTEXITCODE -eq 0) { break }
    Start-Sleep -Seconds 1
}
if ($LASTEXITCODE -ne 0) { throw "Postgres não ficou pronto." }

# 2. Backend: dependências, migrações, logins de menor privilégio
Push-Location (Join-Path $root "backend")
try {
    uv sync --locked
    $env:MIGRATION_DATABASE_URL = "postgresql+psycopg://basho:demo_throwaway@127.0.0.1:${DbPort}/basho"
    uv run python -m alembic upgrade head
    $roles = @"
DO `$`$ BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'basho_api_login') THEN
    CREATE ROLE basho_api_login LOGIN PASSWORD 'api_demo' IN ROLE basho_api;
  END IF;
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'basho_worker_login') THEN
    CREATE ROLE basho_worker_login LOGIN PASSWORD 'worker_demo' IN ROLE basho_worker;
  END IF;
END `$`$;
"@
    docker exec $container psql -U basho -d basho -q -v ON_ERROR_STOP=1 -c $roles

    $env:DATABASE_URL = "postgresql+psycopg://basho_api_login:api_demo@127.0.0.1:${DbPort}/basho"
    $env:TENANT_ID = $tenant
    $env:REVIEWER_IDENTITY_SECRET = $identitySecret
    # Sem LLM real a API não chama modelo nenhum; as chaves só precisam existir.
    if (-not $env:ANTHROPIC_API_KEY) { $env:ANTHROPIC_API_KEY = "demo-no-llm" }
    if (-not $env:FEATHERLESS_API_KEY) { $env:FEATHERLESS_API_KEY = "demo-no-llm" }
    if (-not $env:FEATHERLESS_BASE_URL) { $env:FEATHERLESS_BASE_URL = "http://127.0.0.1:9/v1" }
    if (-not $env:CHECKER_MODEL) { $env:CHECKER_MODEL = "demo-checker" }
    if (-not $env:GITHUB_TOKEN) { $env:GITHUB_TOKEN = "demo-no-github" }

    # 3. Seed sintético (idempotente)
    $seed = uv run python -m basho.seed | Select-Object -Last 1 | ConvertFrom-Json
    $projectId = $seed.project_id

    # 3.1 Servidor falso de Drive/Notion (opcional, só ensaio)
    if ($FakeProviders) {
        $keyScript = Join-Path $logs "make_fake_sa.py"
        @'
import json, sys
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
pem = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()).decode()
open(sys.argv[1], "w").write(json.dumps({"client_email": "basho-demo@projeto-falso.iam.gserviceaccount.com", "private_key": pem}))
'@ | Set-Content -Encoding ascii $keyScript
        $saFile = Join-Path $logs "fake-sa.json"
        uv run python $keyScript $saFile
        Stop-Port $FakePort
        Start-Process -WindowStyle Hidden -FilePath "uv" -ArgumentList @("run", "python", (Join-Path $root "scripts/dev/fake_providers.py"), "$FakePort") `
            -RedirectStandardOutput (Join-Path $logs "fake.out.log") -RedirectStandardError (Join-Path $logs "fake.err.log")
        $env:GOOGLE_SERVICE_ACCOUNT_JSON = $saFile
        $env:GOOGLE_DRIVE_API_URL = "http://127.0.0.1:$FakePort"
        $env:GOOGLE_TOKEN_URI = "http://127.0.0.1:$FakePort/token"
        $env:NOTION_TOKEN = "fake-notion-token"
        $env:NOTION_API_URL = "http://127.0.0.1:$FakePort"
    }

    # 4. API
    Stop-Port $ApiPort
    $env:API_PORT = "$ApiPort"
    Start-Process -WindowStyle Hidden -FilePath "uv" -ArgumentList @("run", "python", "-m", "basho.serve") `
        -RedirectStandardOutput (Join-Path $logs "api.out.log") -RedirectStandardError (Join-Path $logs "api.err.log")

    # 4.1 Worker (login próprio, membro de basho_worker): publica e roda o agente
    Stop-Pids
    $env:DATABASE_URL = "postgresql+psycopg://basho_worker_login:worker_demo@127.0.0.1:${DbPort}/basho"
    $worker = Start-Process -PassThru -WindowStyle Hidden -FilePath "uv" -ArgumentList @("run", "python", "-m", "basho.agent.worker") `
        -RedirectStandardOutput (Join-Path $logs "worker.out.log") -RedirectStandardError (Join-Path $logs "worker.err.log")
    $worker.Id | Set-Content (Join-Path $logs "worker.pid")
} finally { Pop-Location }

for ($i = 0; $i -lt 30; $i++) {
    try { if ((Invoke-RestMethod "http://127.0.0.1:$ApiPort/health").status -eq "ok") { break } } catch { Start-Sleep -Seconds 1 }
}

# 5. Front em modo api (NEXT_PUBLIC_* entram no build)
Push-Location (Join-Path $root "frontend")
try {
    if (-not (Test-Path node_modules)) { npm ci }
    $env:NEXT_PUBLIC_DATA_SOURCE = "api"
    $env:NEXT_PUBLIC_API_URL = "http://127.0.0.1:$ApiPort"
    $env:NEXT_PUBLIC_BASHO_PROJECT_ID = $projectId
    $env:BASHO_API_URL = "http://127.0.0.1:$ApiPort"
    $env:BASHO_DEMO_REVIEWERS = "${researcher}:researcher,${manager}:manager"
    npm run build
    Stop-Port $WebPort
    Start-Process -WindowStyle Hidden -FilePath "npx.cmd" -ArgumentList @("next", "start", "-p", "$WebPort") `
        -RedirectStandardOutput (Join-Path $logs "web.out.log") -RedirectStandardError (Join-Path $logs "web.err.log")
} finally { Pop-Location }

Start-Sleep -Seconds 4
Write-Host ""
Write-Host "Demo no ar" -ForegroundColor Green
Write-Host "  Projeto da demo : $projectId"
Write-Host "  Front           : http://127.0.0.1:$WebPort  (gerente: /gerente/pendencias, /gerente/dossie)"
Write-Host "  API             : http://127.0.0.1:$ApiPort/docs"
Write-Host "  Integrações     : http://127.0.0.1:$WebPort/gerente/integracoes  (cole o link da pasta/página)"
if ($FakeProviders) { Write-Host "  Servidor FALSO  : http://127.0.0.1:$FakePort/_state  (documentos gerados abrem aqui)" }
Write-Host "  Logs            : $logs"
Write-Host "  Parar           : powershell -File scripts/demo-up.ps1 -Down"
