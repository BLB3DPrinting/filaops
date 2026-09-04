#Requires -Version 7
<#
.SYNOPSIS
    Run the FilaOps Playwright UI suite against an isolated local stack.

.DESCRIPTION
    Stands up a throwaway PostgreSQL database (filaops_e2e), a backend in
    test mode on port 8001, and a Vite dev server on port 5174, then runs
    frontend/tests/e2e with Playwright and tears everything down.

    Your normal dev servers on 8000 / 5173 and the `filaops` database are
    never touched. The script hardcodes the e2e database name and refuses
    to run if anything resolves to a name containing "prod".

    Database credentials (DB_HOST/DB_PORT/DB_USER/DB_PASSWORD) are read from
    backend/.env. Only DB_NAME is overridden.

.PARAMETER Grep
    Playwright --grep filter, e.g. -Grep smoke

.PARAMETER Spec
    One or more spec paths (relative to frontend/), e.g.
    -Spec tests/e2e/pages/smoke.spec.ts

.PARAMETER Fresh
    Drop and recreate filaops_e2e before running (default: reuse if present).

.PARAMETER CopyFrom
    Create filaops_e2e as a copy of this database (Postgres TEMPLATE) instead
    of an empty migrated schema. Requires NO active connections to the source
    database, so stop the dev backend first. Example: -CopyFrom filaops

.PARAMETER Headed
    Run Chromium visibly instead of headless.

.PARAMETER InstallBrowsers
    Run `npx playwright install chromium` if the browser is missing
    (downloads ~150 MB from Microsoft's CDN).

.PARAMETER KeepServers
    Leave the e2e backend/frontend running after the tests (for debugging).

.PARAMETER SkipTests
    Bring the stack up, verify health, and tear it down without running
    Playwright. Useful to validate the environment.

.EXAMPLE
    pwsh scripts/e2e-local.ps1 -Grep smoke
    pwsh scripts/e2e-local.ps1 -Fresh -CopyFrom filaops -Spec tests/e2e/pages/orders.spec.ts -Headed
#>
[CmdletBinding()]
param(
    [string]   $Grep,
    [string[]] $Spec,
    [switch]   $Fresh,
    [string]   $CopyFrom,
    [switch]   $Headed,
    [switch]   $InstallBrowsers,
    [switch]   $KeepServers,
    [switch]   $SkipTests
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

# ---------------------------------------------------------------- constants
$E2E_DB        = 'filaops_e2e'
$BACKEND_PORT  = 8001
$FRONTEND_PORT = 5174
$BACKEND_URL   = "http://localhost:$BACKEND_PORT"
$FRONTEND_URL  = "http://localhost:$FRONTEND_PORT"

$RepoRoot   = Split-Path -Parent $PSScriptRoot
$BackendDir = Join-Path $RepoRoot 'backend'
$FrontDir   = Join-Path $RepoRoot 'frontend'
$LogDir     = Join-Path $RepoRoot 'test-results' 'e2e-local'
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

function Step($msg) { Write-Host "`n==> $msg" -ForegroundColor Cyan }
function Ok($msg)   { Write-Host "    $msg" -ForegroundColor Green }
function Warn($msg) { Write-Host "    $msg" -ForegroundColor Yellow }

# ---------------------------------------------------------------- preflight
Step 'Preflight'
foreach ($tool in 'python', 'node', 'npm') {
    if (-not (Get-Command $tool -ErrorAction SilentlyContinue)) {
        throw "Required tool not on PATH: $tool"
    }
}
# psql: prefer PATH, else the newest PostgreSQL install under Program Files.
$psqlCmd = Get-Command psql -ErrorAction SilentlyContinue
$PsqlExe = if ($psqlCmd) { $psqlCmd.Source } else { $null }
if (-not $PsqlExe) {
    $PsqlExe = Get-ChildItem "$env:ProgramFiles\PostgreSQL\*\bin\psql.exe" -ErrorAction SilentlyContinue |
        Sort-Object { [int]($_.Directory.Parent.Name) } -Descending | Select-Object -First 1 -ExpandProperty FullName
}
if (-not $PsqlExe) { throw 'psql not found on PATH or under Program Files\PostgreSQL' }

$envFile = Join-Path $BackendDir '.env'
if (-not (Test-Path $envFile)) { throw "backend/.env not found. Copy backend/.env.example and fill in DB_* values." }
$dotenv = @{}
foreach ($line in Get-Content $envFile) {
    if ($line -match '^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)\s*$') {
        $dotenv[$Matches[1]] = $Matches[2].Trim().Trim('"').Trim("'")
    }
}
$DbHost = if ($dotenv.DB_HOST) { $dotenv.DB_HOST } else { 'localhost' }
$DbPort = if ($dotenv.DB_PORT) { $dotenv.DB_PORT } else { '5432' }
$DbUser = if ($dotenv.DB_USER) { $dotenv.DB_USER } else { 'postgres' }
if (-not $dotenv.DB_PASSWORD) { throw 'DB_PASSWORD missing from backend/.env' }

# $CopyFrom is interpolated into SQL below: restrict it to a plain PostgreSQL
# identifier (letters, digits, underscore) so it can never carry quotes,
# semicolons, or whitespace, and reject anything that looks like production.
if ($CopyFrom -and $CopyFrom -notmatch '^[A-Za-z_][A-Za-z0-9_]{0,62}$') {
    throw "Invalid -CopyFrom database name '$CopyFrom': only letters, digits and underscores are allowed."
}
if ($E2E_DB -match 'prod' -or $CopyFrom -match 'prod') {
    throw 'Refusing to touch a database whose name contains "prod".'
}
Ok "Postgres $DbHost`:$DbPort as $DbUser, e2e database: $E2E_DB"

$env:PGPASSWORD = $dotenv.DB_PASSWORD
function Psql([string]$sql, [string]$db = 'postgres') {
    $out = & $PsqlExe -h $DbHost -p $DbPort -U $DbUser -d $db -v ON_ERROR_STOP=1 -tAc $sql 2>&1
    if ($LASTEXITCODE -ne 0) { throw "psql failed: $out" }
    return ($out | Out-String).Trim()
}

# Playwright browser check
Push-Location $FrontDir
try {
    $chromiumOk = & node -e "const {chromium}=require('@playwright/test');process.stdout.write(require('fs').existsSync(chromium.executablePath())?'yes':'no')"
    if ($chromiumOk -ne 'yes' -and -not $SkipTests) {
        if ($InstallBrowsers) {
            Step 'Installing Playwright Chromium'
            & npx.cmd playwright install chromium
            if ($LASTEXITCODE -ne 0) { throw 'playwright install failed' }
            $chromiumOk = 'yes'
        } else {
            throw "Playwright Chromium is not installed. Re-run with -InstallBrowsers (downloads ~150 MB) or run: npx playwright install chromium"
        }
    }
    if ($chromiumOk -eq 'yes') { Ok 'Playwright Chromium present' } else { Warn 'Playwright Chromium missing (tests skipped, so continuing)' }
} finally { Pop-Location }

# ---------------------------------------------------------------- database
Step "Database $E2E_DB"
$exists = (Psql "SELECT 1 FROM pg_database WHERE datname = '$E2E_DB'") -eq '1'

if ($exists -and $Fresh) {
    Psql "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = '$E2E_DB' AND pid <> pg_backend_pid()" | Out-Null
    Psql "DROP DATABASE $E2E_DB" | Out-Null
    Ok "Dropped existing $E2E_DB"
    $exists = $false
}

if (-not $exists) {
    if ($CopyFrom) {
        $conns = Psql "SELECT count(*) FROM pg_stat_activity WHERE datname = '$CopyFrom'"
        if ([int]$conns -gt 0) {
            throw "Cannot copy from '$CopyFrom': it has $conns active connection(s). Stop the dev backend (and psql sessions) first, or omit -CopyFrom for an empty migrated schema."
        }
        Psql ('CREATE DATABASE ' + $E2E_DB + ' TEMPLATE "' + $CopyFrom + '"') | Out-Null
        Ok "Created $E2E_DB as a copy of $CopyFrom"
    } else {
        Psql "CREATE DATABASE $E2E_DB" | Out-Null
        Ok "Created empty $E2E_DB"
    }
}

# Always bring the schema to head (no-op on an up-to-date copy).
Push-Location $BackendDir
try {
    $env:DB_NAME = $E2E_DB
    & python -m alembic upgrade head 2>&1 | Tee-Object -FilePath (Join-Path $LogDir 'alembic.log') | Select-Object -Last 1
    if ($LASTEXITCODE -ne 0) { throw 'alembic upgrade head failed (see test-results/e2e-local/alembic.log)' }
    Ok 'Schema at head'
} finally { Pop-Location }

# ---------------------------------------------------------------- servers
$procs = @()
function Wait-Http([string]$url, [int]$seconds = 60) {
    $deadline = (Get-Date).AddSeconds($seconds)
    while ((Get-Date) -lt $deadline) {
        try {
            $r = Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 3
            if ($r.StatusCode -lt 500) { return $r }
        } catch { Start-Sleep -Milliseconds 500 }
    }
    throw "Timed out waiting for $url"
}
function Stop-Tree($p) {
    if ($p -and -not $p.HasExited) { & taskkill /PID $p.Id /T /F 2>&1 | Out-Null }
}

try {
    Step "Backend on :$BACKEND_PORT (test mode, DB $E2E_DB)"
    $env:DB_NAME              = $E2E_DB
    $env:ENVIRONMENT          = 'e2e'
    $env:ALLOW_TEST_DATA_WIPE = 'true'       # cleanup endpoint only removes admin@filaops.test
    $env:ALLOWED_ORIGINS      = "$FRONTEND_URL,http://127.0.0.1:$FRONTEND_PORT"
    $env:FRONTEND_URL         = $FRONTEND_URL
    $env:SENTRY_DSN           = ''
    $backend = Start-Process -FilePath 'python' `
        -ArgumentList @('-m', 'uvicorn', 'app.main:app', '--host', '127.0.0.1', '--port', "$BACKEND_PORT") `
        -WorkingDirectory $BackendDir -PassThru -WindowStyle Hidden `
        -RedirectStandardOutput (Join-Path $LogDir 'backend.out.log') `
        -RedirectStandardError  (Join-Path $LogDir 'backend.err.log')
    $procs += $backend
    $health = Wait-Http "$BACKEND_URL/health"
    Ok "health: $($health.Content)"
    $testHealth = Wait-Http "$BACKEND_URL/api/v1/test/health" 15
    Ok "test endpoints enabled: HTTP $($testHealth.StatusCode)"

    Step "Frontend on :$FRONTEND_PORT (VITE_API_URL=$BACKEND_URL)"
    $env:VITE_API_URL = $BACKEND_URL
    $frontend = Start-Process -FilePath 'cmd' `
        -ArgumentList @('/c', "npm run dev -- --port $FRONTEND_PORT --strictPort") `
        -WorkingDirectory $FrontDir -PassThru -WindowStyle Hidden `
        -RedirectStandardOutput (Join-Path $LogDir 'frontend.out.log') `
        -RedirectStandardError  (Join-Path $LogDir 'frontend.err.log')
    $procs += $frontend
    Wait-Http "$FRONTEND_URL/admin/login" | Out-Null
    Ok 'frontend serving'

    if ($SkipTests) {
        Warn 'SkipTests set: stack verified, not running Playwright.'
        $exit = 0
    } else {
        Step 'Playwright'
        $env:BASE_URL = $FRONTEND_URL
        $env:API_URL  = $BACKEND_URL
        $pwArgs = @('playwright', 'test', '--project=chromium')
        if ($Grep)   { $pwArgs += @('--grep', $Grep) }
        if ($Headed) { $pwArgs += '--headed' }
        if ($Spec)   { $pwArgs += $Spec }
        Write-Host "    npx $($pwArgs -join ' ')"
        Push-Location $FrontDir
        try {
            & npx.cmd @pwArgs
            $exit = $LASTEXITCODE
        } finally { Pop-Location }
        if ($exit -eq 0) { Ok 'Playwright passed' } else { Warn "Playwright exit code $exit" }
        Warn "Report: cd frontend; npx playwright show-report"
    }
}
finally {
    if ($KeepServers) {
        Warn "KeepServers: backend pid $($backend.Id) on $BACKEND_URL, frontend pid $($frontend.Id) on $FRONTEND_URL"
        Warn "Stop with: taskkill /PID <pid> /T /F"
    } else {
        Step 'Teardown'
        foreach ($p in $procs) { Stop-Tree $p }
        Ok 'servers stopped'
    }
    Remove-Item Env:PGPASSWORD, Env:DB_NAME, Env:ENVIRONMENT, Env:ALLOW_TEST_DATA_WIPE, Env:ALLOWED_ORIGINS, Env:FRONTEND_URL, Env:VITE_API_URL, Env:BASE_URL, Env:API_URL -ErrorAction SilentlyContinue
}

exit $exit
