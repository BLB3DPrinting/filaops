# start-frontend.ps1 (PowerShell 5+)
$ErrorActionPreference = "Stop"

Write-Host "[frontend] Starting dev server..." -ForegroundColor Cyan

# Get the script directory (repo root) - works when called directly or from another script
$scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$frontendDir = Join-Path $scriptRoot "frontend"
if (-not (Test-Path $frontendDir)) {
    Write-Host "[frontend] 'frontend' folder not found." -ForegroundColor Red
    exit 1
}

# ensure Node is available and on the supported major (mirrors frontend/package.json "engines")
$requiredNodeMajor = 24
if (-not (Get-Command node -ErrorAction SilentlyContinue)) {
    Write-Host "[frontend] Node.js not found on PATH." -ForegroundColor Red
    Write-Host "          Install Node $requiredNodeMajor LTS from https://nodejs.org/en/download" -ForegroundColor Yellow
    exit 1
}
$nodeVersion = (& node --version).Trim()
$nodeMajor = 0
if ($nodeVersion -match '^v(\d+)\.') { $nodeMajor = [int]$Matches[1] }
if ($nodeMajor -lt $requiredNodeMajor) {
    Write-Host "[frontend] Node.js $nodeVersion is too old; $requiredNodeMajor or newer is required." -ForegroundColor Red
    Write-Host "          Install Node $requiredNodeMajor LTS from https://nodejs.org/en/download (or: nvm install $requiredNodeMajor)" -ForegroundColor Yellow
    exit 1
}

# figure out which script to run
$pkgPath = Join-Path $frontendDir "package.json"
if (-not (Test-Path $pkgPath)) {
    Write-Host "[frontend] package.json not found." -ForegroundColor Red
    exit 1
}

$pkg = Get-Content $pkgPath -Raw | ConvertFrom-Json
$scriptToRun = $null
if ($pkg.scripts.dev) { $scriptToRun = "dev" }
elseif ($pkg.scripts.start) { $scriptToRun = "start" }
elseif ($pkg.scripts."serve") { $scriptToRun = "serve" }

if (-not $scriptToRun) {
    Write-Host "[frontend] Could not find a dev/start script in package.json." -ForegroundColor Red
    Write-Host "          Define one under 'scripts' (e.g. \"dev\": \"vite\" or \"next dev\")." -ForegroundColor Yellow
    exit 1
}

# Check if node_modules exists and has the required binaries
$nodeModulesPath = Join-Path $frontendDir "node_modules"
$viteBinPath = Join-Path $frontendDir "node_modules\.bin\vite.cmd"
$needsInstall = $false

if (-not (Test-Path $nodeModulesPath)) {
    Write-Host "[frontend] node_modules not found." -ForegroundColor Yellow
    $needsInstall = $true
}
elseif (-not (Test-Path $viteBinPath)) {
    Write-Host "[frontend] Dependencies appear incomplete (vite not found in node_modules\.bin\)." -ForegroundColor Yellow
    $needsInstall = $true
}

if ($needsInstall) {
    Write-Host "[frontend] Installing dependencies..." -ForegroundColor Yellow
    Push-Location $frontendDir
    try {
        if (Test-Path "package-lock.json") {
            npm ci
        }
        else {
            npm install
        }
        if ($LASTEXITCODE -ne 0) {
            Write-Host "[frontend] Failed to install dependencies. Exit code: $LASTEXITCODE" -ForegroundColor Red
            Pop-Location
            Write-Host "[frontend] Press any key to exit..." -ForegroundColor Gray
            $null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
            exit 1
        }
        Write-Host "[frontend] Dependencies installed." -ForegroundColor Green
    }
    catch {
        Write-Host "[frontend] Failed to install dependencies. Error: $_" -ForegroundColor Red
        Pop-Location
        Write-Host "[frontend] Press any key to exit..." -ForegroundColor Gray
        $null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
        exit 1
    }
    Pop-Location
}

Push-Location $frontendDir
try {
    # helpful hint about common ports
    Write-Host "`n[frontend] If this is Vite: http://localhost:5173" -ForegroundColor DarkGray
    Write-Host "[frontend] If this is Next.js: http://localhost:3000" -ForegroundColor DarkGray
    Write-Host "[frontend] If this is CRA: http://localhost:3000`n" -ForegroundColor DarkGray

    # run it in the current console so logs stream visibly
    npm run $scriptToRun
    if ($LASTEXITCODE -ne 0) {
        Write-Host "`n[frontend] Error: npm run $scriptToRun failed with exit code $LASTEXITCODE" -ForegroundColor Red
        Write-Host "[frontend] Make sure dependencies are installed. Try running: .\install-frontend.ps1" -ForegroundColor Yellow
        Write-Host "[frontend] Press any key to exit..." -ForegroundColor Gray
        $null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
    }
}
catch {
    Write-Host "`n[frontend] Error: $_" -ForegroundColor Red
    Write-Host "[frontend] Make sure dependencies are installed. Try running: .\install-frontend.ps1" -ForegroundColor Yellow
    Write-Host "[frontend] Press any key to exit..." -ForegroundColor Gray
    $null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
}
finally {
    Pop-Location
}
